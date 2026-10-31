"""Xử lý âm thanh: chuyển đổi mọi định dạng qua ffmpeg, cắt lặng, chuẩn hoá,
chấm điểm chất lượng mẫu, ghép nối, xuất WAV/MP3."""
import os
import subprocess
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import TMP

_FFMPEG = None


def ffmpeg_exe() -> str:
    global _FFMPEG
    if _FFMPEG is None:
        try:
            import imageio_ffmpeg
            _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            _FFMPEG = "ffmpeg"
    return _FFMPEG


def run_ffmpeg(args: list) -> None:
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y"] + [str(a) for a in args]
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    p = subprocess.run(cmd, capture_output=True, creationflags=flags)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg lỗi: " + p.stderr.decode("utf-8", "ignore")[-800:])


def tmp_path(suffix=".wav") -> Path:
    d = TMP / "work"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{uuid.uuid4().hex}{suffix}"


def to_wav(src, dst=None, sr: int = 44100, mono: bool = True) -> Path:
    """Chuyển bất kỳ file âm thanh/video nào sang WAV PCM16."""
    dst = Path(dst) if dst else tmp_path()
    args = ["-i", src, "-vn", "-ar", sr]
    if mono:
        args += ["-ac", 1]
    args += ["-c:a", "pcm_s16le", dst]
    run_ffmpeg(args)
    return dst


def load(path, sr: int = 44100) -> np.ndarray:
    """Đọc mọi định dạng -> mono float32 tại sr."""
    p = Path(path)
    try:
        data, file_sr = sf.read(str(p), dtype="float32", always_2d=True)
        data = data.mean(axis=1)
        if file_sr == sr:
            return data
    except Exception:
        pass
    w = to_wav(p, sr=sr)
    data, _ = sf.read(str(w), dtype="float32")
    try:
        w.unlink()
    except OSError:
        pass
    return data


def save_wav(path, audio: np.ndarray, sr: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.clip(audio, -1, 1).astype(np.float32), sr, subtype="PCM_16")
    return path


def duration(path) -> float:
    try:
        return sf.info(str(path)).duration
    except Exception:
        return len(load(path, 16000)) / 16000.0


# ---------------------------------------------------------------- phân tích
def frame_rms_db(x: np.ndarray, sr: int, win: float = 0.025, hop: float = 0.010) -> np.ndarray:
    n, h = int(sr * win), int(sr * hop)
    if len(x) < n:
        return np.array([-100.0])
    idx = np.arange(0, len(x) - n, h)
    frames = np.stack([x[i:i + n] for i in idx])
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    return 20 * np.log10(rms + 1e-12)


def trim_silence(x: np.ndarray, sr: int, top_db: float = 40.0, keep: float = 0.05) -> np.ndarray:
    """Cắt lặng đầu/cuối, giữ lại `keep` giây đệm."""
    if len(x) == 0:
        return x
    db = frame_rms_db(x, sr)
    thr = db.max() - top_db
    voiced = np.where(db > thr)[0]
    if len(voiced) == 0:
        return x
    hop = int(sr * 0.010)
    start = max(0, voiced[0] * hop - int(keep * sr))
    end = min(len(x), (voiced[-1] + 3) * hop + int(keep * sr))
    return x[start:end]


def compress_internal_silence(x: np.ndarray, sr: int, max_sil: float = 0.6, top_db: float = 40.0) -> np.ndarray:
    """Rút ngắn các khoảng lặng bên trong dài hơn max_sil (dùng cho mẫu tham chiếu)."""
    db = frame_rms_db(x, sr)
    thr = db.max() - top_db
    hop = int(sr * 0.010)
    silent = db <= thr
    out, i, n = [], 0, len(silent)
    last = 0
    while i < n:
        if silent[i]:
            j = i
            while j < n and silent[j]:
                j += 1
            if (j - i) * hop > max_sil * sr:
                keep = int(max_sil * sr / 2)
                out.append(x[last: i * hop + keep])
                last = j * hop - keep
            i = j
        else:
            i += 1
    out.append(x[last:])
    return np.concatenate(out) if out else x


def loudness_normalize(x: np.ndarray, sr: int, target: float = -20.0) -> np.ndarray:
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        l = meter.integrated_loudness(x)
        if np.isfinite(l):
            x = pyln.normalize.loudness(x, l, target)
    except Exception:
        peak = np.abs(x).max() + 1e-9
        x = x / peak * 0.7
    peak = np.abs(x).max()
    if peak > 0.97:
        x = x * (0.97 / peak)
    return x.astype(np.float32)


def max_internal_silence(x: np.ndarray, sr: int, top_db: float = 45.0) -> float:
    db = frame_rms_db(x, sr)
    if len(db) < 3:
        return 0.0
    thr = db.max() - top_db
    silent = db <= thr
    # bỏ lặng đầu/cuối
    v = np.where(~silent)[0]
    if len(v) == 0:
        return len(x) / sr
    silent = silent[v[0]: v[-1] + 1]
    best = cur = 0
    for s in silent:
        cur = cur + 1 if s else 0
        best = max(best, cur)
    return best * 0.010


def quality_score(x: np.ndarray, sr: int) -> dict:
    """Chấm điểm một đoạn mẫu giọng (0-100) để chọn mẫu tham chiếu tốt nhất."""
    dur = len(x) / sr
    if dur < 0.5:
        return {"score": 0.0, "snr": 0.0, "clip": 0.0, "speech": 0.0, "dur": dur}
    db = frame_rms_db(x, sr)
    noise = np.percentile(db, 10)
    speech = np.percentile(db, 90)
    snr = float(speech - noise)
    clip_ratio = float((np.abs(x) > 0.985).mean())
    speech_ratio = float((db > speech - 25).mean())
    # điểm SNR: 15dB -> 0, 45dB -> 1
    s_snr = np.clip((snr - 15) / 30, 0, 1)
    # độ dài lý tưởng 4-15s
    if dur < 2:
        s_dur = dur / 2 * 0.5
    elif dur < 4:
        s_dur = 0.5 + (dur - 2) / 4
    elif dur <= 15:
        s_dur = 1.0
    else:
        s_dur = max(0.6, 1 - (dur - 15) / 60)
    s_clip = np.clip(1 - clip_ratio * 200, 0, 1)
    s_speech = np.clip(speech_ratio / 0.6, 0, 1)
    score = 100 * (0.5 * s_snr + 0.2 * s_dur + 0.15 * s_clip + 0.15 * s_speech)
    return {"score": round(float(score), 1), "snr": round(snr, 1), "clip": round(clip_ratio * 100, 3),
            "speech": round(speech_ratio * 100, 1), "dur": round(dur, 2)}


def fade(x: np.ndarray, sr: int, ms: float = 8.0) -> np.ndarray:
    n = min(int(sr * ms / 1000), len(x) // 2)
    if n <= 0:
        return x
    x = x.copy()
    ramp = np.linspace(0, 1, n, dtype=np.float32)
    x[:n] *= ramp
    x[-n:] *= ramp[::-1]
    return x


def silence(sec: float, sr: int) -> np.ndarray:
    return np.zeros(int(max(0.0, sec) * sr), dtype=np.float32)


# ---------------------------------------------------------------- xuất file
def export_final(src_wav, out_base, speed: float = 1.0, lufs: float = -14.0, sr: int = 48000,
                 want_wav=True, want_mp3=True, mp3_bitrate="320k") -> dict:
    """Áp tốc độ + chuẩn hoá loudness (EBU R128) rồi xuất WAV/MP3."""
    out_base = Path(out_base)
    out_base.parent.mkdir(parents=True, exist_ok=True)
    filters = []
    if abs(speed - 1.0) > 1e-3:
        s = speed
        while s > 2.0:
            filters.append("atempo=2.0"); s /= 2.0
        while s < 0.5:
            filters.append("atempo=0.5"); s /= 0.5
        filters.append(f"atempo={s:.4f}")
    if lufs is not None:
        filters.append(f"loudnorm=I={lufs}:TP=-1.5:LRA=11")
    af = ",".join(filters) if filters else "anull"
    res = {}
    master = out_base.with_suffix(".wav")
    run_ffmpeg(["-i", src_wav, "-af", af, "-ar", sr, "-ac", 1, "-c:a", "pcm_s16le", master])
    if want_mp3:
        mp3 = out_base.with_suffix(".mp3")
        run_ffmpeg(["-i", master, "-c:a", "libmp3lame", "-b:a", mp3_bitrate, mp3])
        res["mp3"] = mp3
    if want_wav:
        res["wav"] = master
    elif master.exists():
        master.unlink()
    return res

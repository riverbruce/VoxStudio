"""Huấn luyện LoRA cho một giọng (tuỳ chọn, cho độ giống cao nhất).
Cần >= 5-10 phút giọng sạch. Quy trình:
 1) Whisper cắt các đoạn mẫu thành câu 2-15s kèm lời thoại -> dataset/manifest.jsonl
 2) Chạy script huấn luyện chính thức của VoxCPM (scripts/train_voxcpm_finetune.py)
    trong tiến trình riêng, giới hạn VRAM như app
 3) Gắn checkpoint mới nhất vào giọng"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

from . import audio_utils as au
from . import engine, voices
from .config import LOGS, ROOT, SETTINGS, SRC, TTS_MODEL_DIR

_PROC = {}


def raw_dir(vid: str) -> Path:
    d = voices.voice_dir(vid) / "lora" / "raw"
    d.mkdir(parents=True, exist_ok=True)
    return d


def add_training_files(vid: str, files: list, denoise: bool = False, log=print) -> None:
    """Thêm âm thanh dài (5–60 phút, mọi định dạng) chỉ dùng cho huấn luyện LoRA.
    Không ảnh hưởng tới tham chiếu clone thường của giọng."""
    rd = raw_dir(vid)
    n = len(list(rd.glob("*.wav")))
    for f in files or []:
        n += 1
        work = au.to_wav(f, sr=44100)
        if denoise:
            dn = au.tmp_path()
            if engine.denoise(work, dn):
                work = au.to_wav(dn, sr=44100)
        x = au.load(work, 44100)
        x = au.loudness_normalize(au.trim_silence(x, 44100), 44100, -20.0)
        au.save_wav(rd / f"{n:03d}.wav", x, 44100)
        (rd / f"{n:03d}.txt").write_text(Path(f).name, encoding="utf-8")
        log(f"+ {Path(f).name}: {len(x) / 44100 / 60:.1f} phút")


def training_summary(vid: str) -> str:
    if not vid:
        return ""
    meta = voices.load_meta(vid)
    clips = sum(c.get("dur", 0) for c in meta.get("clips", []) if c.get("enabled", True))
    raw = sum(au.duration(f) for f in raw_dir(vid).glob("*.wav"))
    tot = (clips + raw) / 60
    st = "✅ đủ" if tot >= 10 else ("🟡 tạm được" if tot >= 5 else "🔴 còn thiếu")
    return (f"**Dữ liệu huấn luyện:** đoạn mẫu của giọng {clips / 60:.1f} phút + âm thanh huấn luyện {raw / 60:.1f} phút "
            f"= **{tot:.1f} phút** ({st}; khuyến nghị ≥ 10 phút)")


def _split_by_silence(x, sr=16000, min_len=4.0, max_len=12.0):
    """Cắt audio dài thành các câu 3–12s tại chỗ ngắt hơi (lặng)."""
    db = au.frame_rms_db(x, sr)
    if len(db) < 10:
        return []
    thr = min(max(db.max() - 38, np.percentile(db, 3) + 8), db.max() - 18)
    hop = int(sr * 0.01)
    silent = db <= thr
    cuts, start, i = [], 0, 0
    while i < len(silent):
        pos = i * hop
        seg = (pos - start) / sr
        if silent[i] and seg >= min_len:
            j = i
            while j < len(silent) and silent[j]:
                j += 1
            mid = ((i + j) // 2) * hop
            cuts.append((start, mid)); start = mid; i = j
            continue
        if seg >= max_len:
            # không có chỗ lặng: cắt tại điểm nhỏ tiếng nhất trong 2s cuối
            lo = max(int(start / hop), i - 200)
            k = lo + int(np.argmin(db[lo:i + 1])) if i > lo else i
            cuts.append((start, k * hop)); start = k * hop
        i += 1
    if (len(x) - start) / sr >= 1.5:
        cuts.append((start, len(x)))
    return cuts


def _segment(src, lang, ds, prefix, rows, log, progress=None):
    x = au.load(src, 16000)
    total = 0.0
    pieces = _split_by_silence(x)
    for k, (a, b) in enumerate(pieces):
        seg = au.trim_silence(x[a:b], 16000, keep=0.08)
        dur = len(seg) / 16000
        if dur < 1.5 or dur > 15:
            continue
        text = engine.transcribe_array(seg, language=lang)
        if len(text.strip()) < 2:
            continue
        name = f"{prefix}_{k:04d}.wav"
        au.save_wav(ds / name, seg, 16000)
        rows.append({"audio": str((ds / name).resolve()), "text": text, "duration": round(dur, 3)})
        total += dur
        if progress:
            progress(len(rows))
    log(f"{Path(src).name}: {len(pieces)} câu, dùng được {total / 60:.1f} phút")
    return total


def prepare_dataset(vid: str, use_clips: bool = True, log=print, progress=None) -> dict:
    from .langs import whisper_name
    d = voices.voice_dir(vid)
    meta = voices.load_meta(vid)
    lang = whisper_name(meta.get("ref_lang", "vi"))
    ds = d / "lora" / "dataset"
    ds.mkdir(parents=True, exist_ok=True)
    for old in ds.glob("*.wav"):
        try:
            old.unlink()
        except OSError:
            pass
    rows, total = [], 0.0
    if use_clips:
        for c in meta["clips"]:
            if c.get("enabled", True):
                total += _segment(d / "clips" / c["file"], lang, ds, "clip_" + c["file"][:-4], rows, log, progress)
    for f in sorted(raw_dir(vid).glob("*.wav")):
        total += _segment(f, lang, ds, "raw_" + f.stem, rows, log, progress)
    man = ds / "manifest.jsonl"
    man.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    log(f"Dataset: {len(rows)} câu, tổng {total / 60:.1f} phút")
    return {"manifest": str(man), "n": len(rows), "minutes": round(total / 60, 2)}


def start_training(vid: str, iters: int = 1000, lr: float = 1e-4, rank: int = 32) -> str:
    d = voices.voice_dir(vid)
    man = d / "lora" / "dataset" / "manifest.jsonl"
    if not man.exists():
        raise RuntimeError("Chưa chuẩn bị dataset.")
    if vid in _PROC and _PROC[vid].poll() is None:
        raise RuntimeError("Đang huấn luyện giọng này rồi.")
    engine.unload_all()   # nhường toàn bộ VRAM cho tiến trình huấn luyện
    out = d / "lora" / "checkpoints"
    if out.exists():   # huấn luyện mới -> cất bản cũ sang chỗ khác (không xoá)
        shutil.move(str(out), str(d / "lora" / f"checkpoints_old_{int(time.time())}"))
    cfg = {
        "pretrained_path": str(TTS_MODEL_DIR), "train_manifest": str(man), "val_manifest": "",
        "sample_rate": 16000, "out_sample_rate": 48000, "batch_size": 1, "grad_accum_steps": 16,
        "num_workers": 0, "preprocessing_num_workers": 1, "num_iters": int(iters), "log_interval": 10,
        "valid_interval": 10 ** 9, "save_interval": max(100, int(iters) // 4), "learning_rate": float(lr),
        "weight_decay": 0.01, "warmup_steps": min(100, int(iters) // 10), "max_steps": int(iters),
        "max_batch_tokens": 2048, "max_grad_norm": 1.0, "save_path": str(out),
        "tensorboard": str(out / "logs"), "lambdas": {"loss/diff": 1.0, "loss/stop": 1.0},
        "lora": {"enable_lm": True, "enable_dit": True, "enable_proj": False, "r": int(rank),
                 "alpha": int(rank), "dropout": 0.0},
    }
    cfg_file = d / "lora" / "train_config.yaml"
    cfg_file.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")  # JSON hợp lệ với YAML
    logf = LOGS / f"lora_{vid}.log"
    env = dict(os.environ)
    v = SETTINGS.get("vram_limit_gb", "auto")
    env["VOXSTUDIO_VRAM_GB"] = str(v)
    env["PYTHONIOENCODING"] = "utf-8"
    script = SRC / "scripts" / "train_voxcpm_finetune.py"
    cmd = [sys.executable, str(ROOT / "app" / "train_wrapper.py"), str(script), "--config_path", str(cfg_file)]
    fh = open(logf, "w", encoding="utf-8")
    flags = 0x08000000 if os.name == "nt" else 0
    _PROC[vid] = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, cwd=str(SRC), env=env,
                                  creationflags=flags)
    return str(logf)


_STATE = {}   # vid -> {"phase", "msg", "t0", "iters", "n_rows"}


def _state_file(vid):
    return voices.voice_dir(vid) / "lora" / "status.json"


def _save_state(vid):
    try:
        st = {k: v for k, v in _STATE.get(vid, {}).items() if k != "thread"}
        _state_file(vid).write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _load_state(vid):
    if vid in _STATE:
        return _STATE[vid]
    f = _state_file(vid)
    if f.exists():
        try:
            _STATE[vid] = json.loads(f.read_text(encoding="utf-8"))
            if _STATE[vid].get("phase") in ("prep", "train"):   # app đã bị tắt giữa chừng
                _STATE[vid]["phase"] = "stopped"
        except Exception:
            _STATE[vid] = {}
    return _STATE.get(vid, {})


def is_busy() -> bool:
    return any(st.get("phase") in ("prep", "train") for st in _STATE.values())


def start_all(vid: str, iters=1000, lr=1e-4, rank=32, use_clips=True):
    """1 nút: chuẩn bị dữ liệu (Whisper) -> huấn luyện (tiến trình riêng) -> tự gắn vào giọng."""
    if not vid:
        raise RuntimeError("Hãy chọn giọng trước.")
    if is_busy():
        raise RuntimeError("Đang có một giọng khác đang huấn luyện. Mỗi lần chỉ huấn luyện được 1 giọng.")
    meta = voices.load_meta(vid)
    mins = (sum(c.get("dur", 0) for c in meta.get("clips", []) if c.get("enabled", True)) * bool(use_clips)
            + sum(au.duration(f) for f in raw_dir(vid).glob("*.wav"))) / 60
    if mins < 5:
        raise RuntimeError(f"Mới có {mins:.1f} phút giọng nói — cần ít nhất 5 phút (tốt nhất ≥ 10 phút). "
                           "Hãy thêm âm thanh ở ô ① rồi thử lại.")
    st = {"phase": "prep", "msg": "Đang chuẩn bị", "t0": time.time(), "iters": int(iters), "n_rows": 0,
          "rank": int(rank)}
    _STATE[vid] = st
    _save_state(vid)

    def run():
        try:
            def prog(n):
                st["n_rows"] = n
            r = prepare_dataset(vid, use_clips=use_clips, log=lambda *a: None, progress=prog)
            st["minutes"] = r["minutes"]
            if r["n"] < 20:
                raise RuntimeError(f"Chỉ cắt được {r['n']} câu dùng được ({r['minutes']} phút) — quá ít để huấn luyện. "
                                   "Hãy thêm âm thanh giọng sạch, nói rõ.")
            st.update(phase="train", t_train=time.time())
            _save_state(vid)
            start_training(vid, iters, lr, rank)
        except Exception as e:
            from .friendly import humanize
            engine.log(f"LoRA lỗi: {e}")
            st.update(phase="error", msg=humanize(e).lstrip("❌ ").strip())
            _save_state(vid)

    threading.Thread(target=run, daemon=True).start()


def stop_training(vid: str):
    p = _PROC.get(vid)
    if p and p.poll() is None:
        p.terminate()
    st = _STATE.get(vid)
    if st:
        st.update(phase="stopped", msg="Bạn đã dừng huấn luyện.")
        _save_state(vid)


def _fmt_eta(sec):
    sec = max(0, int(sec))
    if sec >= 3600:
        return f"{sec // 3600} giờ {sec % 3600 // 60} phút"
    if sec >= 60:
        return f"{sec // 60} phút"
    return f"{sec} giây"


def _bar(pct):
    n = int(pct / 4)
    return "`" + "█" * n + "░" * (25 - n) + "`"


def friendly_status(vid: str) -> tuple:
    """(markdown dễ hiểu, log kỹ thuật) cho giao diện."""
    if not vid:
        return "Chọn một giọng để xem trạng thái huấn luyện.", ""
    st = _load_state(vid)
    logf = LOGS / f"lora_{vid}.log"
    raw = logf.read_text(encoding="utf-8", errors="ignore") if logf.exists() else ""
    tail = "\n".join(raw.splitlines()[-40:])
    meta = voices.load_meta(vid)
    phase = st.get("phase")
    p = _PROC.get(vid)

    if phase == "prep":
        return (f"### ⏳ Bước 1/2 · Đang chuẩn bị dữ liệu\nĐang cắt âm thanh thành từng câu và nghe lại lời "
                f"(đã xử lý **{st.get('n_rows', 0)} câu**).\n\n<span class='hint'>Việc này mất vài phút, cứ để app chạy.</span>", tail)

    if phase == "train" and p is not None and p.poll() is None:
        steps = [int(m) for m in re.findall(r"\[train\] step (\d+)", raw)]
        iters = st.get("iters", 1000)
        if not steps:
            return ("### ⏳ Bước 2/2 · Đang khởi động huấn luyện\nĐang nạp model lên card đồ hoạ (khoảng 1–2 phút)...\n\n"
                    "<span class='hint'>Trong lúc huấn luyện, card đồ hoạ được dành hết cho việc này — tạm thời "
                    "chưa đọc kịch bản được.</span>", tail)
        step = steps[-1]
        pct = min(100.0, 100 * step / max(1, iters))
        el = time.time() - st.get("t_train", st.get("t0", time.time()))
        eta = el / max(step, 1) * (iters - step)
        return (f"### 🔥 Bước 2/2 · Đang huấn luyện giọng\n{_bar(pct)} **{pct:.0f}%** · bước {step}/{iters} · "
                f"còn khoảng **{_fmt_eta(eta)}**\n\n<span class='hint'>Có thể để máy chạy và làm việc khác "
                "(không chơi game nặng). Xong sẽ tự gắn vào giọng.</span>", tail)

    if phase == "train" and p is not None and p.poll() is not None:
        # tiến trình vừa kết thúc -> phân tích kết quả
        if p.returncode == 0 and "[VOXSTUDIO] DONE" in raw:
            try:
                attach_latest(vid)
                st.update(phase="done", finished=time.strftime("%H:%M %d/%m"))
            except Exception:
                st.update(phase="error", msg="Huấn luyện chạy xong nhưng không thấy kết quả được lưu.")
        elif "OOM" in raw or "out of memory" in raw.lower():
            st.update(phase="error", msg="oom")
        else:
            st.update(phase="error", msg="crash")
        _save_state(vid)
        phase = st["phase"]

    if phase == "done" or (phase in (None, "stopped") and meta.get("lora")):
        on = "ĐANG BẬT" if meta.get("use_lora") else "đang tắt"
        when = st.get("finished", "")
        return (f"### ✅ Giọng này đã được huấn luyện{(' lúc ' + when) if when else ''}\n"
                f"Bản huấn luyện **{on}**. Hãy bấm **▶️ Nghe thử** ở trên và bật/tắt ô *Dùng bản huấn luyện* "
                "để so sánh giọng nào giống hơn.", tail)
    if phase == "error":
        m = st.get("msg", "")
        if m == "oom":
            return ("### ❌ Huấn luyện dừng vì card đồ hoạ hết bộ nhớ\n💡 Cách khắc phục:\n"
                    "1. Đóng game, Chrome, CapCut... rồi bấm **Bắt đầu huấn luyện** lại.\n"
                    "2. Nếu vẫn bị: mở *Tuỳ chỉnh nâng cao* chọn **Rank 16** (hoặc 8) rồi thử lại.", tail)
        if m == "crash":
            return ("### ❌ Huấn luyện bị lỗi giữa chừng\nHãy thử lại một lần. Nếu vẫn bị, mở *Chi tiết kỹ thuật* bên dưới "
                    f"và gửi file `logs/lora_{vid}.log` cho người hỗ trợ.", tail)
        return f"### ❌ Chưa huấn luyện được\n{m}", tail
    if phase == "stopped":
        return "### ⏸️ Huấn luyện đã dừng\nBấm **Bắt đầu huấn luyện** để làm lại từ đầu.", tail
    return ("### 💤 Giọng này chưa được huấn luyện\nThêm âm thanh (≥ 10 phút) rồi bấm **🚀 Bắt đầu huấn luyện**. "
            "Không bắt buộc — giọng vẫn dùng tốt khi chưa huấn luyện.", tail)


def attach_latest(vid: str) -> str:
    d = voices.voice_dir(vid) / "lora" / "checkpoints"
    cands = []
    if (d / "latest").exists():
        cands.append(d / "latest")
    cands += sorted(d.glob("step_*"), reverse=True)
    for c in cands:
        if (c / "lora_weights.safetensors").exists() or (c / "lora_weights.ckpt").exists():
            meta = voices.load_meta(vid)
            meta["lora"] = str(c.resolve())
            meta["use_lora"] = True
            voices.save_meta(vid, meta)
            return str(c)
    raise RuntimeError("Chưa có kết quả huấn luyện nào cho giọng này.")

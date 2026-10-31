"""Thư viện giọng: mỗi giọng = 1 thư mục trong voices/ gồm
  originals/   file gốc người dùng đưa vào (mọi định dạng)
  clips/       bản đã chuẩn hoá (mono 44.1kHz, cắt lặng, chuẩn loudness)
  reference.wav   tham chiếu tổng hợp tốt nhất (ghép từ nhiều đoạn)
  prompt.wav      đoạn mẫu đơn tốt nhất + prompt_text (cho Ultimate Cloning)
  lora/        (tuỳ chọn) trọng số LoRA đã huấn luyện
  meta.json
"""
import json
import re
import shutil
import time
import unicodedata
from pathlib import Path

import numpy as np

from . import audio_utils as au
from .config import VOICES

SR = 44100


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\-]+", "_", s).strip("_").lower()
    return s or f"voice_{int(time.time())}"


def voice_dir(vid: str) -> Path:
    return VOICES / vid


def load_meta(vid: str) -> dict:
    f = voice_dir(vid) / "meta.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def save_meta(vid: str, meta: dict):
    meta["updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    (voice_dir(vid) / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def list_voices(lang: str | None = None) -> list:
    """[(nhãn hiển thị, id)] — nhãn kèm cờ ngôn ngữ. lang: chỉ lấy giọng dành cho ngôn ngữ đó."""
    from .langs import LANGS
    items = []
    for d in sorted(VOICES.iterdir()) if VOICES.exists() else []:
        if (d / "meta.json").exists() and not d.name.startswith("_"):
            m = load_meta(d.name)
            tl = m.get("target_lang", "vi")
            if lang and tl != lang:
                continue
            items.append((d.name, m, LANGS.get(tl, ("", "🌐"))[1]))
    names = [m.get("name", vid).strip().lower() for vid, m, _ in items]
    out = []
    for vid, m, flag in items:
        name = m.get("name", vid)
        dup = names.count(name.strip().lower()) > 1
        # tên trùng -> thêm mã giọng để không nhầm (VD: DE1 · de1_2)
        extra = f" · {vid}" if dup else ""
        ok = "" if m.get("reference") else " (chưa xong)"
        out.append((f"{flag} {name}{extra}{ok}", vid))
    return out


def describe(vid: str) -> str:
    """Mô tả đầy đủ 1 giọng (dùng trong hộp xác nhận xoá)."""
    from .langs import label
    m = load_meta(vid)
    total = sum(c.get("dur", 0) for c in m.get("clips", []))
    return (f"**{m.get('name', vid)}** (mã `{vid}`) · {label(m.get('target_lang', 'vi'))} · "
            f"{len(m.get('clips', []))} đoạn mẫu ({total:.0f}s) · tạo lúc {m.get('created', '?')}")


def list_trash() -> list:
    t = VOICES / "_trash"
    out = []
    for d in sorted(t.iterdir(), reverse=True) if t.exists() else []:
        if (d / "meta.json").exists():
            m = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            ts = d.name.rsplit("_", 1)[-1]
            when = time.strftime("%d/%m %H:%M", time.localtime(int(ts))) if ts.isdigit() else ""
            out.append((f"{m.get('name', d.name)} · xoá lúc {when}", d.name))
    return out


def restore_voice(tid: str) -> str:
    src = VOICES / "_trash" / tid
    base = tid.rsplit("_", 1)[0] if tid.rsplit("_", 1)[-1].isdigit() else tid
    vid, i = base, 2
    while voice_dir(vid).exists():
        vid = f"{base}_{i}"; i += 1
    shutil.move(str(src), str(voice_dir(vid)))
    m = load_meta(vid); m["id"] = vid; save_meta(vid, m)
    return vid


def purge_voice(tid: str):
    """Xoá vĩnh viễn 1 giọng trong thùng rác."""
    p = (VOICES / "_trash" / tid).resolve()
    if p.parent != (VOICES / "_trash").resolve() or not p.exists():
        raise ValueError("Không tìm thấy giọng trong thùng rác.")
    shutil.rmtree(p)


def set_langs(vid: str, ref_lang: str, target_lang: str):
    m = load_meta(vid)
    m["ref_lang"], m["target_lang"] = ref_lang, target_lang
    save_meta(vid, m)


def quick_create(name: str, ref_lang: str, target_lang: str, files: list, denoise: bool = False, log=print) -> str:
    """1 nút: tạo giọng + thêm mẫu + tạo tham chiếu tốt nhất."""
    vid = create_voice(name, ref_lang=ref_lang, target_lang=target_lang)
    add_clips(vid, files, denoise, log=log)
    build_reference(vid, log=log)
    return vid


def create_voice(name: str, note: str = "", ref_lang: str = "vi", target_lang: str = "vi") -> str:
    vid = slug(name)
    base = vid
    i = 2
    while voice_dir(vid).exists():
        vid = f"{base}_{i}"; i += 1
    d = voice_dir(vid)
    for sub in ("originals", "clips", "lora"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    save_meta(vid, {"name": name, "id": vid, "note": note, "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "ref_lang": ref_lang, "target_lang": target_lang,
                    "clips": [], "reference": None, "prompt": None, "lora": None, "use_lora": False,
                    "mode": "ultimate", "cfg_value": 2.0, "timesteps": 10})
    return vid


def rename_voice(vid: str, new_name: str):
    m = load_meta(vid); m["name"] = new_name; save_meta(vid, m)


def delete_voice(vid: str):
    """Không xoá hẳn: chuyển vào voices/_trash để có thể khôi phục."""
    if not vid or not voice_dir(vid).exists() or vid.startswith("_") or "/" in vid or "\\" in vid:
        raise ValueError(f"Không tìm thấy giọng '{vid}'.")
    trash = VOICES / "_trash"
    trash.mkdir(exist_ok=True)
    shutil.move(str(voice_dir(vid)), str(trash / f"{vid}_{int(time.time())}"))


def add_clips(vid: str, files: list, denoise: bool = False, log=print) -> list:
    """Nhận mọi file âm thanh/video, chuẩn hoá và chấm điểm từng đoạn."""
    from . import engine
    d = voice_dir(vid)
    meta = load_meta(vid)
    added = []
    for f in files or []:
        src = Path(f)
        idx = len(meta["clips"]) + 1
        orig = d / "originals" / f"{idx:03d}_{src.name}"
        shutil.copy2(src, orig)
        work = au.to_wav(orig, sr=SR)
        if denoise:
            dn = au.tmp_path()
            if engine.denoise(work, dn):
                work = au.to_wav(dn, sr=SR)
        x = au.load(work, SR)
        x = au.trim_silence(x, SR, top_db=40)
        x = au.compress_internal_silence(x, SR, max_sil=0.6)
        x = au.loudness_normalize(x, SR, -20.0)
        clip = d / "clips" / f"{idx:03d}.wav"
        au.save_wav(clip, x, SR)
        q = au.quality_score(x, SR)
        entry = {"file": clip.name, "source": src.name, "enabled": True, "transcript": "", **q}
        meta["clips"].append(entry)
        added.append(entry)
        log(f"+ {src.name}: {q['dur']}s, điểm {q['score']}")
    save_meta(vid, meta)
    return added


def split_long_clip(vid: str, clip_name: str, max_sec: float = 15.0) -> int:
    """Cắt đoạn mẫu dài (>20s) thành các đoạn 6-15s tại chỗ lặng."""
    d = voice_dir(vid)
    meta = load_meta(vid)
    entry = next(c for c in meta["clips"] if c["file"] == clip_name)
    x = au.load(d / "clips" / clip_name, SR)
    db = au.frame_rms_db(x, SR)
    thr = db.max() - 35
    hop = int(SR * 0.01)
    cuts, start = [], 0
    i = 0
    while i < len(db):
        seg_len = (i * hop - start) / SR
        if seg_len >= 6 and db[i] <= thr:
            cuts.append((start, i * hop)); start = i * hop
        elif seg_len >= max_sec:
            cuts.append((start, i * hop)); start = i * hop
        i += 1
    cuts.append((start, len(x)))
    entry["enabled"] = False
    n = 0
    for a, b in cuts:
        seg = au.trim_silence(x[a:b], SR)
        if len(seg) / SR < 2.0:
            continue
        n += 1
        idx = len(meta["clips"]) + 1
        name = f"{idx:03d}.wav"
        au.save_wav(d / "clips" / name, seg, SR)
        meta["clips"].append({"file": name, "source": f"{entry['source']} (phần {n})", "enabled": True,
                              "transcript": "", **au.quality_score(seg, SR)})
    save_meta(vid, meta)
    return n


def build_reference(vid: str, target_sec: float = 20.0, max_sec: float = 30.0, use_whisper: bool = True,
                    manual_prompt_text: str = "", log=print) -> dict:
    """Tạo tham chiếu chất lượng nhất từ nhiều đoạn:
    1) lọc các đoạn đang bật, xếp theo điểm chất lượng
    2) reference.wav = ghép các đoạn tốt nhất tới ~target_sec (đặc trưng âm sắc đầy đủ hơn)
    3) prompt.wav = đoạn đơn tốt nhất 4-15s + lời thoại (Ultimate Cloning, giữ ngữ điệu)"""
    d = voice_dir(vid)
    meta = load_meta(vid)
    clips = [c for c in meta["clips"] if c.get("enabled", True) and c.get("dur", 0) >= 1.0]
    if not clips:
        raise ValueError("Chưa có đoạn mẫu nào hợp lệ.")
    clips.sort(key=lambda c: c["score"], reverse=True)
    # bỏ đoạn kém hẳn so với đoạn tốt nhất
    best = clips[0]["score"]
    good = [c for c in clips if c["score"] >= best - 25] or clips[:1]

    # reference
    parts, total, used = [], 0.0, []
    for c in good:
        x = au.load(d / "clips" / c["file"], SR)
        room = max_sec - total
        if room < 1.5:
            break
        if len(x) / SR > room:
            x = x[: int(room * SR)]
            x = au.fade(x, SR, 30)
        parts.append(au.fade(x, SR, 10))
        parts.append(au.silence(0.35, SR))
        total += len(x) / SR + 0.35
        used.append(c["file"])
        if total >= target_sec:
            break
    ref = np.concatenate(parts[:-1]) if len(parts) > 1 else parts[0]
    ref = au.loudness_normalize(ref, SR, -20.0)
    au.save_wav(d / "reference.wav", ref, SR)
    log(f"reference.wav: {len(ref) / SR:.1f}s từ {len(used)} đoạn")

    # prompt (đoạn đơn tốt nhất, ưu tiên 4-15s)
    cand = [c for c in good if 3.0 <= c["dur"] <= 15.0] or good
    pc = max(cand, key=lambda c: c["score"])
    px = au.load(d / "clips" / pc["file"], SR)
    if len(px) / SR > 15:
        px = au.fade(px[: int(15 * SR)], SR, 30)
    au.save_wav(d / "prompt.wav", px, SR)
    text = (manual_prompt_text or "").strip()
    if not text and use_whisper:
        try:
            from . import engine
            from .langs import whisper_name
            text = engine.transcribe(d / "prompt.wav", language=whisper_name(meta.get("ref_lang", "vi")))
            log(f"Whisper nhận dạng lời đoạn mẫu: {text}")
        except Exception as e:
            log(f"Không chạy được Whisper: {e}")
    meta["reference"] = {"file": "reference.wav", "clips": used, "dur": round(len(ref) / SR, 2)}
    meta["prompt"] = {"file": "prompt.wav", "clip": pc["file"], "text": text, "dur": round(len(px) / SR, 2)}
    if not text and meta.get("mode") == "ultimate":
        meta["mode"] = "reference"
    save_meta(vid, meta)
    return meta


def voice_inputs(vid: str, mode: str | None = None, read_lang: str | None = None) -> dict:
    """Trả về tham số clone cho engine.synthesize theo chế độ.
    Nếu đọc ngôn ngữ khác ngôn ngữ của giọng mẫu -> dùng chế độ Reference (chỉ âm sắc),
    tránh mang ngữ điệu/lời của đoạn mẫu sang ngôn ngữ khác."""
    d = voice_dir(vid)
    meta = load_meta(vid)
    mode = mode or meta.get("mode", "ultimate")
    if read_lang and read_lang != meta.get("ref_lang", "vi"):
        mode = "reference"
    out = {"ref_wav": None, "prompt_wav": None, "prompt_text": None, "lora_path": None}
    if meta.get("reference") and (d / "reference.wav").exists():
        out["ref_wav"] = str(d / "reference.wav")
    p = meta.get("prompt") or {}
    if mode == "ultimate" and p.get("text") and (d / "prompt.wav").exists():
        out["prompt_wav"] = str(d / "prompt.wav")
        out["prompt_text"] = p["text"]
    if meta.get("use_lora") and meta.get("lora") and Path(meta["lora"]).exists():
        out["lora_path"] = meta["lora"]
    if not out["ref_wav"] and not out["prompt_wav"]:
        raise ValueError("Giọng này chưa có tham chiếu — hãy bấm 'Tạo tham chiếu tốt nhất' trước.")
    return out


def clips_table(vid: str) -> list:
    meta = load_meta(vid)
    rows = []
    for c in meta.get("clips", []):
        rows.append([c["file"], c.get("source", ""), c.get("dur", 0), c.get("score", 0), c.get("snr", 0),
                     "✅" if c.get("enabled", True) else "⛔"])
    return rows


def toggle_clip(vid: str, clip: str):
    meta = load_meta(vid)
    for c in meta["clips"]:
        if c["file"] == clip:
            c["enabled"] = not c.get("enabled", True)
    save_meta(vid, meta)


# ---------------------------------------------------------------- chia sẻ giọng giữa các máy
def export_voice(vid: str) -> Path:
    """Đóng gói giọng thành 1 file .voxvoice (zip) để gửi sang máy khác.
    Gồm: thông tin, đoạn mẫu đã xử lý, tham chiếu, và bản huấn luyện LoRA đang dùng (nếu có)."""
    import zipfile
    from .config import OUTPUTS
    d = voice_dir(vid)
    meta = load_meta(vid)
    out_dir = OUTPUTS / "_giong_da_xuat"
    out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]+", "_", meta.get("name", vid)).strip("_") or vid
    out = out_dir / f"{safe}.voxvoice"
    m2 = dict(meta)
    lora_dir = Path(meta["lora"]) if meta.get("lora") else None
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in ["reference.wav", "prompt.wav"]:
            if (d / f).exists():
                z.write(d / f, f)
        for c in meta.get("clips", []):
            p = d / "clips" / c["file"]
            if p.exists():
                z.write(p, f"clips/{c['file']}")
        if lora_dir and lora_dir.exists():
            for f in lora_dir.iterdir():
                if f.suffix in (".safetensors", ".ckpt", ".json") and "optimizer" not in f.name and "scheduler" not in f.name:
                    z.write(f, f"lora/active/{f.name}")
            m2["lora"] = "lora/active"
        z.writestr("meta.json", json.dumps(m2, indent=2, ensure_ascii=False))
        z.writestr("VOXSTUDIO_VOICE", "1")
    return out


def import_voice(file) -> str:
    """Nhập giọng từ file .voxvoice. Trả về mã giọng mới."""
    import zipfile
    with zipfile.ZipFile(file) as z:
        names = z.namelist()
        if "meta.json" not in names:
            raise ValueError("File này không phải giọng VoxStudio (.voxvoice).")
        meta = json.loads(z.read("meta.json").decode("utf-8"))
        vid = slug(meta.get("name", "giong"))
        base, i = vid, 2
        while voice_dir(vid).exists():
            vid = f"{base}_{i}"; i += 1
        d = voice_dir(vid)
        d.mkdir(parents=True)
        for n in names:
            if n.endswith("/") or ".." in n or n.startswith("/") or ":" in n:
                continue
            target = d / n
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(n))
    for sub in ("originals", "clips", "lora"):
        (d / sub).mkdir(exist_ok=True)
    meta["id"] = vid
    if meta.get("lora"):
        meta["lora"] = str((d / meta["lora"]).resolve())
    meta["imported"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_meta(vid, meta)
    (d / "VOXSTUDIO_VOICE").unlink(missing_ok=True)
    return vid

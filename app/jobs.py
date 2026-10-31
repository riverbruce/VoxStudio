"""Dự án đọc kịch bản dài (từ vài giây tới nhiều giờ):
- chia đoạn -> sinh từng đoạn -> lưu ngay ra đĩa (tắt máy / lỗi vẫn chạy tiếp được)
- kiểm tra chất lượng từng đoạn (độ dài bất thường, lặng dài, rè) + tự sinh lại
- tuỳ chọn Whisper nghe lại so lời (CER) và sinh lại đoạn đọc sai
- ghép với khoảng nghỉ tự nhiên, chuẩn hoá loudness, xuất WAV + MP3 + SRT (+ từng chương)"""
import json
import re
import threading
import time
import traceback
from pathlib import Path

import numpy as np

from . import audio_utils as au
from . import emotion, engine, voices
from .chunker import chunk_text, estimate_seconds
from .config import OUTPUTS, PRESETS, PROJECTS, SETTINGS
from .langs import spaced, whisper_name
from .subtitles import DEFAULT_SUB, build_cues, voiced_curve, write_srt
from .vi_normalize import normalize


# ---------------------------------------------------------------- tiện ích
def _now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def job_dir(jid: str) -> Path:
    return PROJECTS / jid


def load_job(jid: str) -> dict:
    return json.loads((job_dir(jid) / "job.json").read_text(encoding="utf-8"))


def save_job(job: dict):
    p = job_dir(job["id"]) / "job.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def list_jobs() -> list:
    out = []
    for d in sorted(PROJECTS.iterdir(), reverse=True) if PROJECTS.exists() else []:
        f = d / "job.json"
        if f.exists():
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
                done = sum(1 for c in j["chunks"] if c["status"] == "done")
                out.append((f"{j['name']} · {done}/{len(j['chunks'])} · {j['status']}", j["id"]))
            except Exception:
                pass
    return out


def safe_name(s: str, n: int = 80) -> str:
    """Tên file/thư mục hợp lệ trên Windows (không ký tự cấm, không kết thúc bằng dấu cách/dấu chấm)."""
    s = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "_", s or "")
    s = re.sub(r"\s+", " ", s).strip(" ._")[:n].strip(" ._")
    if s.upper() in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?i)(com|lpt)\d", s):
        s = "_" + s
    return s or "output"


# ---------------------------------------------------------------- tạo dự án
def _style_for(key: str, text: str, p: dict) -> tuple:
    """(key cảm xúc thực tế, chỉ dẫn tiếng Anh cho VoxCPM2)"""
    inten = p.get("intensity", "Vừa")
    if key.startswith("custom:"):
        return "custom", key[7:].strip()
    if key == "auto":
        k = emotion.detect(text)
        return k, emotion.instruction(k, inten)
    if key == "custom":
        return "custom", emotion.instruction("custom", inten, p.get("emotion_custom", ""))
    return key, emotion.instruction(key, inten)


def create_job(name: str, text: str, voice_id: str, preset: str, mode: str = None, opts: dict = None) -> str:
    opts = dict(opts or {})
    p = dict(PRESETS[preset])
    p.update({k: v for k, v in opts.items() if v is not None})
    from .voices import slug
    jid = time.strftime("%Y%m%d_%H%M%S") + "_" + (slug(name)[:30].strip("_") or "job")
    d = job_dir(jid)
    (d / "chunks").mkdir(parents=True, exist_ok=True)
    (d / "script.txt").write_text(text, encoding="utf-8")
    lang = p.get("lang", "vi")
    raw = chunk_text(emotion.mark_tags(text), max_chars=int(p["max_chars"]), lang=lang)
    chunks = []
    cur = p.get("emotion", "natural")
    for c in raw:
        tag, t = emotion.strip_mark(c["text"])
        if tag:
            cur = tag
        t = t.strip()
        if not t or re.fullmatch(r"[\s.。!?…]*", t):
            if chunks:
                chunks[-1]["pause"] = c["pause"] if c["pause"] != "sentence" else chunks[-1]["pause"]
            continue
        key, style = _style_for(cur, t, p)
        chunks.append({
            "i": len(chunks), "text": t, "tts": normalize(t, lang) if p.get("normalize", True) else t,
            "pause": c["pause"], "chapter": c["chapter"], "chapter_title": c["chapter_title"],
            "emo": key, "style": style,
            "status": "pending", "file": None, "dur": 0.0, "attempts": 0, "qc": "", "cer": None,
        })
    job = {"id": jid, "name": name, "voice": voice_id, "mode": mode, "preset": preset, "params": p,
           "created": _now(), "status": "new", "chunks": chunks, "outputs": {}, "log": []}
    save_job(job)
    return jid


# ---------------------------------------------------------------- QC
def qc_check(x: np.ndarray, sr: int, text: str, lang: str = "vi") -> tuple:
    dur = len(x) / sr
    exp = estimate_seconds(text, lang)
    ratio = dur / exp
    peak = float(np.abs(x).max()) if len(x) else 0.0
    sil = au.max_internal_silence(x, sr) if len(x) else 99
    clip = float((np.abs(x) > 0.995).mean()) if len(x) else 0
    problems = []
    if ratio < 0.45:
        problems.append(f"quá ngắn ({ratio:.2f}x)")
    if ratio > 2.3:
        problems.append(f"quá dài ({ratio:.2f}x) – có thể lặp/lan man")
    if sil > 2.2:
        problems.append(f"lặng {sil:.1f}s")
    if peak < 0.02:
        problems.append("gần như im lặng")
    if clip > 0.002:
        problems.append("rè/vỡ tiếng")
    score = abs(np.log(max(ratio, 1e-3))) + (sil > 2.2) * 2 + (peak < 0.02) * 5 + clip * 100
    return (not problems), ", ".join(problems), float(score), round(dur, 2)


def _plain(s: str, lang: str = "vi") -> str:
    s = normalize(s, lang).lower()
    s = re.sub(r"[^\w]+", "", s, flags=re.U)
    return s.replace("_", "")


def cer(ref: str, hyp: str, lang: str = "vi") -> float:
    r, h = _plain(ref, lang), _plain(hyp, lang)
    if not r:
        return 0.0
    prev = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        cur = [i] + [0] * len(h)
        for j in range(1, len(h) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
        prev = cur
    return prev[-1] / len(r)


# ---------------------------------------------------------------- runner
class Runner:
    def __init__(self):
        self.thread = None
        self.cancel = threading.Event()
        self.state = {"job": None, "msg": "Sẵn sàng", "done": 0, "total": 0, "eta": "", "running": False}

    def busy(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, jid: str, whisper_qc: bool = False, cer_thr: float = 0.25, max_retry: int = 3):
        if self.busy():
            raise RuntimeError("Đang có dự án khác chạy. Hãy dừng hoặc đợi xong.")
        self.cancel.clear()
        self.thread = threading.Thread(target=self._run, args=(jid, whisper_qc, cer_thr, max_retry), daemon=True)
        self.thread.start()

    def stop(self):
        self.cancel.set()

    def _log(self, job, msg):
        engine.log(msg)
        self.state["msg"] = msg
        job.setdefault("log", []).append(f"{time.strftime('%H:%M:%S')} {msg}")
        job["log"] = job["log"][-300:]

    def _gen_chunk(self, job, c, vin, max_retry, seed_base):
        p = job["params"]
        d = job_dir(job["id"])
        best = None
        for a in range(max_retry):
            seed = seed_base + c["i"] * 7 + a * 1009
            style = c.get("style") or ""
            text = f"({style}){c['tts']}" if style else c["tts"]
            # có chỉ dẫn cảm xúc -> dùng chế độ Reference (Ultimate sẽ chép nguyên ngữ điệu đoạn mẫu, át mất cảm xúc)
            pw, pt = (None, None) if style else (vin["prompt_wav"], vin["prompt_text"])
            x, sr = engine.synthesize(text, ref_wav=vin["ref_wav"] or vin["prompt_wav"], prompt_wav=pw,
                                      prompt_text=pt, lora_path=vin["lora_path"],
                                      cfg_value=p.get("cfg_value", 2.0), timesteps=p.get("timesteps", 10), seed=seed)
            ok, why, score, dur = qc_check(x, sr, c["tts"], p.get("lang", "vi"))
            c["attempts"] = c.get("attempts", 0) + 1
            if best is None or score < best[2]:
                best = (x, sr, score, why, dur, ok)
            if ok:
                break
            self._log(job, f"Đoạn {c['i'] + 1}: {why} → sinh lại ({a + 1}/{max_retry})")
        x, sr, score, why, dur, ok = best
        f = d / "chunks" / f"{c['i']:05d}.wav"
        au.save_wav(f, x, sr)
        c.update({"file": f.name, "dur": dur, "status": "done" if ok else "flag", "qc": why, "sr": sr})

    def _run(self, jid, whisper_qc, cer_thr, max_retry):
        job = load_job(jid)
        self.state.update({"job": jid, "running": True, "total": len(job["chunks"])})
        try:
            vin = voices.voice_inputs(job["voice"], job.get("mode"), job["params"].get("lang"))
            seed_base = int(job["params"].get("seed", SETTINGS.get("seed", 1234)))
            job["status"] = "running"
            todo = [c for c in job["chunks"] if c["status"] not in ("done", "flag")]
            self._log(job, f"Bắt đầu: {len(todo)} đoạn cần sinh / tổng {len(job['chunks'])}")
            t0, n = time.time(), 0
            for c in todo:
                if self.cancel.is_set():
                    job["status"] = "paused"
                    self._log(job, "Đã tạm dừng. Bấm 'Chạy / Tiếp tục' để chạy tiếp từ đoạn này.")
                    save_job(job)
                    return
                self._gen_chunk(job, c, vin, max_retry, seed_base)
                n += 1
                done = sum(1 for k in job["chunks"] if k["status"] in ("done", "flag"))
                el = time.time() - t0
                eta = el / n * (len(todo) - n)
                self.state.update({"done": done, "eta": f"{int(eta // 3600)}h{int(eta % 3600 // 60):02d}m{int(eta % 60):02d}s"})
                self.state["msg"] = f"Đoạn {c['i'] + 1}/{len(job['chunks'])} xong ({c['dur']}s) {c['qc']}"
                save_job(job)

            if whisper_qc and not self.cancel.is_set():
                self._whisper_pass(job, vin, cer_thr, max_retry, seed_base)

            self._log(job, "Đang ghép và xuất file...")
            assemble(job)
            job["status"] = "done"
            flags = sum(1 for c in job["chunks"] if c["status"] == "flag")
            self._log(job, f"✅ Hoàn tất. {flags} đoạn cần xem lại (đánh dấu ⚠️)." if flags else "✅ Hoàn tất.")
            save_job(job)
        except Exception as e:
            job["status"] = "error"
            self._log(job, f"❌ Lỗi: {e}")
            engine.log(traceback.format_exc())
            save_job(job)
        finally:
            self.state["running"] = False

    def _whisper_pass(self, job, vin, cer_thr, max_retry, seed_base, rounds=2):
        d = job_dir(job["id"])
        lang = job["params"].get("lang", "vi")
        wl = whisper_name(lang)
        targets = [c for c in job["chunks"] if c["status"] in ("done", "flag")]
        for r in range(rounds):
            self._log(job, f"Whisper kiểm tra lời (vòng {r + 1}): {len(targets)} đoạn")
            bad = []
            for k, c in enumerate(targets):
                if self.cancel.is_set():
                    return
                hyp = engine.transcribe(d / "chunks" / c["file"], language=wl)
                c["cer"] = round(cer(c["tts"], hyp, lang), 3)
                c["asr"] = hyp
                if c["cer"] > cer_thr:
                    bad.append(c)
                self.state["msg"] = f"Whisper {k + 1}/{len(targets)} · CER {c['cer']:.2f}"
            save_job(job)
            if not bad:
                break
            self._log(job, f"{len(bad)} đoạn đọc sai nhiều (CER>{cer_thr}) → sinh lại")
            for c in bad:
                old = (d / "chunks" / c["file"]).read_bytes()
                old_cer = c["cer"]
                self._gen_chunk(job, c, vin, max_retry, seed_base + 50000 * (r + 1))
                hyp = engine.transcribe(d / "chunks" / c["file"], language=wl)
                new_cer = cer(c["tts"], hyp, lang)
                if new_cer > old_cer:   # bản cũ tốt hơn -> giữ bản cũ
                    (d / "chunks" / c["file"]).write_bytes(old)
                    new_cer = old_cer
                c["cer"] = round(new_cer, 3)
                if new_cer > cer_thr:
                    c["status"] = "flag"
                    c["qc"] = (c.get("qc") + "; " if c.get("qc") else "") + f"CER {new_cer:.2f}"
                save_job(job)
            targets = [c for c in bad if c["cer"] > cer_thr]
            if not targets:
                break


RUNNER = Runner()


# ---------------------------------------------------------------- ghép & xuất
def _build(job, chunks, sr):
    p = job["params"]
    pauses = {"comma": p["pause_sentence"] * 0.45, "sentence": p["pause_sentence"],
              "paragraph": p["pause_paragraph"], "chapter": p["pause_chapter"], "end": 0.0}
    d = job_dir(job["id"])
    parts, timings, t = [au.silence(0.15, sr)], [], 0.15
    for c in chunks:
        if not c.get("file"):
            continue
        x = au.load(d / "chunks" / c["file"], sr)
        x = au.fade(au.trim_silence(x, sr, top_db=45, keep=0.03), sr, 8)
        timings.append((t, t + len(x) / sr, c["text"], voiced_curve(x, sr)))
        parts.append(x)
        t += len(x) / sr
        gap = pauses.get(c["pause"], p["pause_sentence"])
        parts.append(au.silence(gap, sr))
        t += gap
    parts.append(au.silence(0.3, sr))
    return np.concatenate(parts), timings


def sub_settings(p: dict) -> dict:
    s = dict(DEFAULT_SUB)
    s.update(p.get("sub", {}))
    return s


def _srt(job, timings, path):
    p = job["params"]
    s = sub_settings(p)
    cues = build_cues(timings, spaced(p.get("lang", "vi")), per_line=s["per_line"], lines=s["lines"],
                      max_dur=s["max_dur"], strip_punct=s["strip_punct"], speed=float(p.get("speed", 1.0)))
    return write_srt(cues, path)


def assemble(job: dict, per_chapter: bool | None = None) -> dict:
    p = job["params"]
    sr = 48000
    speed = float(p.get("speed", 1.0))
    lufs = float(p.get("lufs", -14.0))
    per_chapter = p.get("per_chapter", False) if per_chapter is None else per_chapter
    outdir = OUTPUTS / safe_name(job["name"])
    outdir.mkdir(parents=True, exist_ok=True)
    base = outdir / safe_name(job["name"])
    audio, timings = _build(job, job["chunks"], sr)
    raw = au.tmp_path()
    au.save_wav(raw, audio, sr)
    res = au.export_final(raw, base, speed=speed, lufs=lufs, sr=sr,
                          want_wav=p.get("out_wav", True), want_mp3=p.get("out_mp3", True))
    raw.unlink(missing_ok=True)
    res["srt"] = _srt(job, timings, base.with_suffix(".srt"))
    chapters = sorted({c["chapter"] for c in job["chunks"]})
    if per_chapter and len(chapters) > 1:
        cdir = outdir / "chapters"
        cdir.mkdir(exist_ok=True)
        for ch in chapters:
            cc = [c for c in job["chunks"] if c["chapter"] == ch]
            title = cc[0].get("chapter_title") or f"Phan_{ch}"
            a, tm = _build(job, cc, sr)
            r2 = au.tmp_path(); au.save_wav(r2, a, sr)
            cb = cdir / f"{ch:03d}_{safe_name(title)}"
            au.export_final(r2, cb, speed=speed, lufs=lufs, sr=sr,
                            want_wav=p.get("out_wav", True), want_mp3=p.get("out_mp3", True))
            _srt(job, tm, cb.with_suffix(".srt"))
            r2.unlink(missing_ok=True)
        res["chapters"] = cdir
    job["outputs"] = {k: str(v) for k, v in res.items()}
    job["total_sec"] = round(len(audio) / sr / speed, 1)
    save_job(job)
    return res


def export_srt_only(jid: str, sub: dict) -> str:
    """Xuất lại phụ đề với cài đặt mới, không cần sinh lại audio."""
    job = load_job(jid)
    job["params"]["sub"] = {**sub_settings(job["params"]), **sub}
    _, timings = _build(job, job["chunks"], 48000)
    base = OUTPUTS / safe_name(job["name"]) / safe_name(job["name"])
    base.parent.mkdir(parents=True, exist_ok=True)
    path = _srt(job, timings, base.with_suffix(".srt"))
    job.setdefault("outputs", {})["srt"] = str(path)
    save_job(job)
    return str(path)


def regenerate_chunk(jid: str, i: int, new_text: str | None = None, seed_shift: int = 0) -> dict:
    job = load_job(jid)
    c = job["chunks"][i]
    if new_text is not None and new_text.strip():
        tag, t = emotion.strip_mark(emotion.mark_tags(new_text.strip()).strip())
        t = t.strip() or c["text"]
        if tag:   # người dùng gõ [buồn] ... ở đầu đoạn -> đổi cảm xúc riêng đoạn này
            c["emo"], c["style"] = _style_for(tag, t, job["params"])
        if t != c["text"]:
            c["text"] = t
            c["tts"] = normalize(t, job["params"].get("lang", "vi")) if job["params"].get("normalize", True) else t
    vin = voices.voice_inputs(job["voice"], job.get("mode"), job["params"].get("lang"))
    seed = int(job["params"].get("seed", 1234)) + int(time.time()) % 100000 + seed_shift
    RUNNER._gen_chunk(job, c, vin, 3, seed)
    c["status"] = "done"
    save_job(job)
    return c

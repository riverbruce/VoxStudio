"""Quản lý model trên GPU: VoxCPM2 (TTS), Whisper (nhận dạng lời), ZipEnhancer (khử nhiễu).
- Giới hạn cứng VRAM theo settings (mặc định 10.5GB).
- Chỉ giữ 1 model lớn trên GPU tại một thời điểm (tự hoán đổi TTS <-> Whisper).
- Khoá GPU để các tác vụ không chạy chồng nhau."""
import gc
import inspect
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

from .config import SETTINGS, TTS_MODEL_DIR, WHISPER_MODEL_DIR, ZIPENHANCER_DIR, vram_limit_gb

GPU_LOCK = threading.RLock()
_state = {"tts": None, "tts_lora": None, "whisper": None, "denoiser": None, "vram_set": False}


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, file=sys.stderr, flush=True)


def _torch():
    import torch
    if not _state["vram_set"] and torch.cuda.is_available():
        total = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
        limit = vram_limit_gb(total)
        _state["vram_gb"] = limit
        frac = min(0.99, limit / total)
        torch.cuda.set_per_process_memory_fraction(frac, 0)
        _state["vram_set"] = True
        log(f"GPU: {torch.cuda.get_device_name(0)} | tổng {total:.1f}GB | giới hạn {limit}GB ({frac:.2%})")
    return torch


def gpu_info() -> str:
    try:
        torch = _torch()
        if not torch.cuda.is_available():
            return "⚠️ Không thấy GPU CUDA — đang chạy CPU (rất chậm)."
        used = torch.cuda.memory_allocated(0) / 1024 ** 3
        resv = torch.cuda.memory_reserved(0) / 1024 ** 3
        loaded = [k for k in ("tts", "whisper", "denoiser") if _state[k] is not None]
        return (f"🟢 {torch.cuda.get_device_name(0)} · VRAM dùng {used:.1f}GB (giữ {resv:.1f}GB) / giới hạn "
                f"{_state.get('vram_gb', 0):.1f}GB · Model đang nạp: {', '.join(loaded) or 'chưa có'}")
    except Exception as e:
        return f"Lỗi đọc GPU: {e}"


def _free():
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def unload(name: str):
    if _state.get(name) is not None:
        _state[name] = None
        if name == "tts":
            _state["tts_lora"] = None
        _free()
        log(f"Đã giải phóng {name}")


def unload_all():
    for n in ("tts", "whisper", "denoiser"):
        unload(n)


# ---------------------------------------------------------------- TTS
def get_tts(lora_path: str | None = None):
    """Nạp VoxCPM2 (kèm LoRA nếu có). Tự giải phóng Whisper trước."""
    torch = _torch()
    lora_path = str(lora_path) if lora_path else None
    if _state["tts"] is not None and _state["tts_lora"] == lora_path:
        return _state["tts"]
    unload("whisper")
    unload("tts")
    from voxcpm import VoxCPM
    kwargs = dict(
        voxcpm_model_path=str(TTS_MODEL_DIR),
        zipenhancer_model_path=None,
        enable_denoiser=False,
        optimize=False,          # torch.compile không ổn định trên Windows
    )
    if lora_path:
        cfg_file = Path(lora_path) / "lora_config.json"
        if cfg_file.exists():
            from voxcpm.model.voxcpm import LoRAConfig
            info = json.loads(cfg_file.read_text(encoding="utf-8"))
            kwargs["lora_config"] = LoRAConfig(**info.get("lora_config", {}))
        kwargs["lora_weights_path"] = lora_path
    t = time.time()
    log(f"Đang nạp VoxCPM2{' + LoRA' if lora_path else ''}...")
    _patch_low_ram_init(torch)
    model = VoxCPM(**kwargs)
    gc.collect()
    _state["tts"] = model
    _state["tts_lora"] = lora_path
    log(f"Nạp xong VoxCPM2 sau {time.time() - t:.1f}s")
    return model


_GEN_PARAMS = None


def _patch_low_ram_init(torch):
    """Tạo khung model thẳng ở bfloat16 thay vì float32 -> nạp model tốn ~10GB RAM thay vì ~15GB
    (máy 16GB RAM không còn bị sập khi nạp). Kết quả cuối giống hệt vì model vẫn chạy bfloat16."""
    try:
        from voxcpm.model import voxcpm2 as m2
    except Exception:
        return
    cls = m2.VoxCPM2Model
    if getattr(cls, "_vox_lowram", False):
        return
    orig = cls.__init__

    def init(self, *a, **k):
        prev = torch.get_default_dtype()
        torch.set_default_dtype(torch.bfloat16)
        try:
            orig(self, *a, **k)
        finally:
            torch.set_default_dtype(prev)
    cls.__init__ = init
    cls._vox_lowram = True


def tts_sample_rate() -> int:
    m = _state["tts"]
    return int(getattr(m.tts_model, "sample_rate", 48000)) if m else 48000


def synthesize(text: str, ref_wav=None, prompt_wav=None, prompt_text=None, lora_path=None,
               cfg_value=2.0, timesteps=10, seed=None, max_len=4096) -> tuple:
    """Sinh âm thanh 1 đoạn. Trả về (audio float32, sample_rate)."""
    global _GEN_PARAMS
    with GPU_LOCK:
        model = get_tts(lora_path)
        if _GEN_PARAMS is None:
            _GEN_PARAMS = set(inspect.signature(model._generate).parameters)
        kw = dict(text=text, cfg_value=float(cfg_value), inference_timesteps=int(timesteps),
                  max_len=int(max_len), normalize=False, denoise=False, retry_badcase=True,
                  retry_badcase_max_times=3, retry_badcase_ratio_threshold=6.0)
        if ref_wav:
            kw["reference_wav_path"] = str(ref_wav)
        if prompt_wav and prompt_text:
            kw["prompt_wav_path"] = str(prompt_wav)
            kw["prompt_text"] = prompt_text
        torch = _torch()
        if seed is not None:
            if "seed" in _GEN_PARAMS:
                kw["seed"] = int(seed)
            else:
                torch.manual_seed(int(seed))
                if torch.cuda.is_available():
                    torch.cuda.manual_seed_all(int(seed))
        kw = {k: v for k, v in kw.items() if k in _GEN_PARAMS}
        try:
            wav = model.generate(**kw)
        except torch.cuda.OutOfMemoryError:
            _free()
            log("Hết VRAM, thử lại 1 lần sau khi dọn bộ nhớ...")
            wav = model.generate(**kw)
        return np.asarray(wav, dtype=np.float32), tts_sample_rate()


# ---------------------------------------------------------------- Whisper
def get_whisper():
    torch = _torch()
    if _state["whisper"] is not None:
        return _state["whisper"]
    unload("tts")
    from transformers import pipeline
    src = str(WHISPER_MODEL_DIR) if WHISPER_MODEL_DIR.exists() else "openai/whisper-large-v3-turbo"
    dev = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if torch.cuda.is_available() else torch.float32
    log("Đang nạp Whisper...")
    _state["whisper"] = pipeline("automatic-speech-recognition", model=src, dtype=dtype, device=dev)
    return _state["whisper"]


def transcribe(audio_path, language=None, timestamps=False):
    """Nhận dạng lời. timestamps=True trả về list segment [{text, start, end}]."""
    from .audio_utils import load
    language = language or SETTINGS.get("whisper_language", "vietnamese")
    with GPU_LOCK:
        asr = get_whisper()
        x = load(audio_path, 16000)
        gk = {"task": "transcribe"}
        if language and language != "auto":
            gk["language"] = language
        out = asr({"raw": x, "sampling_rate": 16000}, generate_kwargs=gk,
                  return_timestamps=True if timestamps or len(x) > 30 * 16000 else False,
                  chunk_length_s=30 if len(x) > 30 * 16000 else None, batch_size=4)
    if timestamps:
        segs = []
        for c in out.get("chunks", []):
            st, en = c.get("timestamp", (None, None))
            segs.append({"text": c["text"].strip(), "start": st, "end": en})
        return segs
    return out["text"].strip()


def transcribe_array(x16k, language=None) -> str:
    """Nhận dạng 1 đoạn ngắn (<30s) đã ở dạng mảng 16kHz."""
    language = language or SETTINGS.get("whisper_language", "vietnamese")
    with GPU_LOCK:
        asr = get_whisper()
        gk = {"task": "transcribe"}
        if language and language != "auto":
            gk["language"] = language
        out = asr({"raw": x16k, "sampling_rate": 16000}, generate_kwargs=gk)
    return out["text"].strip()


def transcribe_many(paths, language=None) -> list:
    return [transcribe(p, language) for p in paths]


# ---------------------------------------------------------------- Khử nhiễu
def denoise(in_path, out_path) -> bool:
    """Khử nhiễu bằng ZipEnhancer (model đi kèm VoxCPM). Lỗi -> trả False."""
    try:
        with GPU_LOCK:
            if _state["denoiser"] is None:
                from voxcpm.zipenhancer import ZipEnhancer
                src = str(ZIPENHANCER_DIR) if ZIPENHANCER_DIR.exists() else "iic/speech_zipenhancer_ans_multiloss_16k_base"
                _state["denoiser"] = ZipEnhancer(src)
            _state["denoiser"].enhance(str(in_path), output_path=str(out_path))
        return True
    except Exception as e:
        log(f"Khử nhiễu lỗi (bỏ qua): {e}")
        return False

"""Cấu hình chung của VoxStudio. Mọi đường dẫn đều nằm trong thư mục cài đặt,
không dùng chung cache/model với bất kỳ bản VoxCPM nào khác trên máy."""
import os
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
VOICES = ROOT / "voices"
PROJECTS = ROOT / "projects"
OUTPUTS = ROOT / "outputs"
LOGS = ROOT / "logs"
TMP = ROOT / "tmp"
CACHE = ROOT / "cache"
SRC = ROOT / "VoxCPM-src"

TTS_MODEL_DIR = MODELS / "VoxCPM2"
WHISPER_MODEL_DIR = MODELS / "whisper-large-v3-turbo"
ZIPENHANCER_DIR = MODELS / "zipenhancer"

for _d in (MODELS, VOICES, PROJECTS, OUTPUTS, LOGS, TMP, CACHE):
    _d.mkdir(parents=True, exist_ok=True)

# Cô lập cache: không đụng tới ~/.cache của máy
os.environ.setdefault("HF_HOME", str(CACHE / "hf"))
os.environ.setdefault("MODELSCOPE_CACHE", str(CACHE / "modelscope"))
os.environ.setdefault("TORCH_HOME", str(CACHE / "torch"))
os.environ.setdefault("GRADIO_TEMP_DIR", str(TMP / "gradio"))
os.environ.setdefault("TMP", str(TMP))
os.environ.setdefault("TEMP", str(TMP))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")

SETTINGS_FILE = ROOT / "settings.json"

DEFAULT_SETTINGS = {
    "vram_limit_gb": "auto",      # giới hạn VRAM; "auto" = tổng VRAM của card trừ 1.5GB
    "host": "127.0.0.1",
    "port": 7861,
    "cfg_value": 2.0,
    "inference_timesteps": 10,
    "seed": 1234,
    "whisper_language": "vietnamese",
}


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    else:
        SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    return s


SETTINGS = load_settings()


def vram_limit_gb(total_gb: float) -> float:
    v = SETTINGS.get("vram_limit_gb", "auto")
    try:
        return min(float(v), total_gb)
    except (TypeError, ValueError):
        return max(3.0, total_gb - 1.5)

AUDIO_EXTS = [
    ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac", ".wma", ".aiff", ".aif",
    ".amr", ".webm", ".mp4", ".mkv", ".mov", ".avi", ".3gp", ".m4b", ".caf", ".ac3",
]
TEXT_EXTS = [
    ".txt", ".md", ".srt", ".vtt", ".ass", ".ssa", ".json", ".jsonl", ".csv", ".tsv",
    ".docx", ".pdf", ".epub", ".html", ".htm", ".rtf", ".xml", ".yaml", ".yml", ".lrc", ".sbv",
]

# Preset cho từng loại nội dung
PRESETS = {
    "Short / TikTok / Reels": {
        "max_chars": 160, "pause_sentence": 0.22, "pause_paragraph": 0.45,
        "pause_chapter": 0.8, "speed": 1.08, "lufs": -14.0,
        "sub": {"per_line": 4, "lines": 1, "max_dur": 2.5, "strip_punct": True},
    },
    "YouTube dài / Podcast": {
        "max_chars": 240, "pause_sentence": 0.35, "pause_paragraph": 0.75,
        "pause_chapter": 1.6, "speed": 1.0, "lufs": -14.0,
        "sub": {"per_line": 10, "lines": 1, "max_dur": 5.0, "strip_punct": False},
    },
    "Sách nói / Truyện (chậm, ấm)": {
        "max_chars": 260, "pause_sentence": 0.45, "pause_paragraph": 0.95,
        "pause_chapter": 2.0, "speed": 0.96, "lufs": -16.0,
        "sub": {"per_line": 12, "lines": 2, "max_dur": 6.0, "strip_punct": False},
    },
}

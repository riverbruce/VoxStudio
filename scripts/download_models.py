"""Tai model ve thu muc models/ cua VoxStudio (khong dung cache chung cua may)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / "cache" / "hf"))
os.environ.setdefault("MODELSCOPE_CACHE", str(ROOT / "cache" / "modelscope"))
M = ROOT / "models"
M.mkdir(exist_ok=True)

from huggingface_hub import snapshot_download  # noqa: E402


def hf(repo, dst, **kw):
    for attempt in range(5):
        try:
            print(f"[download] {repo} -> {dst} (lan {attempt + 1})", flush=True)
            snapshot_download(repo_id=repo, local_dir=str(dst), **kw)
            print(f"[ok] {repo}", flush=True)
            return True
        except Exception as e:
            print(f"[retry] {repo}: {e}", flush=True)
    return False


ok = hf("openbmb/VoxCPM2", M / "VoxCPM2")
if not ok:
    print("[FATAL] Khong tai duoc VoxCPM2", flush=True)
    sys.exit(1)

hf("openai/whisper-large-v3-turbo", M / "whisper-large-v3-turbo",
   allow_patterns=["*.json", "*.safetensors", "*.txt", "tokenizer*", "vocab*", "merges*", "normalizer*"])

try:
    from modelscope import snapshot_download as ms_dl
    print("[download] ZipEnhancer (khu nhieu)", flush=True)
    ms_dl("iic/speech_zipenhancer_ans_multiloss_16k_base", local_dir=str(M / "zipenhancer"))
    print("[ok] ZipEnhancer", flush=True)
except Exception as e:
    print(f"[warn] Khong tai duoc ZipEnhancer (tinh nang khu nhieu se tat): {e}", flush=True)
print("[done] models", flush=True)

"""Kiem tra nhanh sau khi cai: GPU, ffmpeg, doc thu 1 cau bang VoxCPM2."""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.config import LOGS, OUTPUTS  # noqa
import faulthandler  # noqa
faulthandler.enable(file=open(LOGS / "crash.log", "a", encoding="utf-8"))
import torch  # noqa
print("torch", torch.__version__, "cuda", torch.cuda.is_available(),
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-", flush=True)
from app import audio_utils as au, engine  # noqa
print("ffmpeg", au.ffmpeg_exe(), flush=True)
t = time.time()
x, sr = engine.synthesize("Xin chào, đây là bài kiểm tra cài đặt VoxStudio.", seed=1)
out = au.save_wav(OUTPUTS / "_selftest.wav", x, sr)
el = time.time() - t
print(f"[selftest ok] {len(x) / sr:.2f}s audio, {el:.1f}s (gom nap model), sr={sr}, file={out}", flush=True)
print(engine.gpu_info(), flush=True)

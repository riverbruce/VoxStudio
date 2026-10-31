"""Chạy script huấn luyện VoxCPM:
- giới hạn VRAM như app
- LoRA: chuyển phần model đóng băng sang bfloat16 (tiết kiệm ~4GB VRAM, chỉ phần LoRA học ở fp32)
- in các dòng mốc [VOXSTUDIO] để giao diện hiển thị tiến độ dễ hiểu"""
import os
import runpy
import sys

import torch

if torch.cuda.is_available():
    total = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
    try:
        lim = min(float(os.environ.get("VOXSTUDIO_VRAM_GB", "auto")), total)
    except ValueError:
        lim = max(3.0, total - 1.5)
    torch.cuda.set_per_process_memory_fraction(min(0.99, lim / total), 0)
    print(f"[VOXSTUDIO] vram {lim} / {total:.1f}", flush=True)

try:
    from voxcpm.model import voxcpm2 as _m2

    _orig = _m2.VoxCPM2Model.from_local.__func__

    def _patched(cls, path, *a, **kw):
        model = _orig(cls, path, *a, **kw)
        if kw.get("training") and getattr(model, "lora_config", None) is not None:
            n = 0
            for name, p in model.named_parameters():
                if "audio_vae" in name or "lora_" in name:
                    continue
                p.data = p.data.to(torch.bfloat16)
                n += 1
            print(f"[VOXSTUDIO] bf16 frozen params: {n}", flush=True)
        return model

    _m2.VoxCPM2Model.from_local = classmethod(_patched)
except Exception as e:  # không chặn huấn luyện nếu patch lỗi
    print(f"[VOXSTUDIO] patch skipped: {e}", flush=True)

script = sys.argv[1]
sys.argv = [script] + sys.argv[2:]
sys.path.insert(0, os.path.dirname(script))
try:
    runpy.run_path(script, run_name="__main__")
    print("[VOXSTUDIO] DONE", flush=True)
except torch.cuda.OutOfMemoryError:
    import traceback
    traceback.print_exc()
    print("[VOXSTUDIO] ERROR OOM", flush=True)
    sys.exit(3)

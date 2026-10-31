"""Phát hành bản cập nhật VoxStudio (chạy trên máy của người phát triển).
Bấm publish.bat -> nhập số phiên bản + ghi chú -> đẩy code lên GitHub -> mọi máy thấy nút "Cập nhật ngay"."""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VF = ROOT / "version.json"


def find_git():
    g = shutil.which("git")
    if g:
        return g
    pats = [os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop\app-*\resources\app\git\cmd\git.exe"),
            r"C:\Program Files\Git\cmd\git.exe"]
    for p in pats:
        m = sorted(glob.glob(p), reverse=True)
        if m:
            return m[0]
    return None


def git(*a, check=True):
    r = subprocess.run([GIT, *a], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip())
    return (r.stdout or "").strip()


def bump(v):
    p = [int(x) for x in re.findall(r"\d+", v)[:3]] + [0, 0, 0]
    return f"{p[0]}.{p[1]}.{p[2] + 1}"


print("=" * 60)
print("  PHÁT HÀNH BẢN CẬP NHẬT VOXSTUDIO")
print("=" * 60)
GIT = find_git()
if not GIT:
    print("\n❌ Chưa có Git. Cài GitHub Desktop (desktop.github.com) hoặc Git for Windows rồi chạy lại.")
    sys.exit(1)
if not (ROOT / ".git").exists():
    print("""
⚠️  Thư mục này chưa được nối với GitHub. Làm 1 lần duy nhất:
  1. Mở GitHub Desktop -> File -> Add local repository -> chọn thư mục:
       {root}
  2. Nếu báo chưa phải repository -> bấm "create a repository" -> Create repository.
     (File .gitignore đã chặn sẵn giọng, model, thư viện — chỉ code được đưa lên.)
  3. Bấm "Publish repository", đặt tên VoxStudio, BỎ TÍCH "Keep this code private" -> Publish.
  4. Chạy lại publish.bat.
""".format(root=ROOT))
    sys.exit(1)

info = json.loads(VF.read_text(encoding="utf-8"))
remote = git("remote", "get-url", "origin", check=False)
m = re.search(r"github\.com[:/]+([^/]+/[^/.]+)", remote or "")
if m:
    info["repo"] = m.group(1)
print(f"\nKho cập nhật: {info.get('repo')}   ·   Bản hiện tại: v{info['version']}")
nv = input(f"Số phiên bản mới [Enter = {bump(info['version'])}]: ").strip() or bump(info["version"])
notes = input("Ghi chú thay đổi (hiện cho người dùng thấy): ").strip() or "Cải thiện & sửa lỗi."
info.update(version=nv, notes=notes, date=time.strftime("%Y-%m-%d"))
VF.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

try:
    git("add", "-A")
    git("commit", "-m", f"v{nv}: {notes}", check=False)
    print("\nĐang đẩy lên GitHub...")
    git("push", "-u", "origin", "HEAD")
    print(f"\n✅ Đã phát hành v{nv}. Các máy khác sẽ thấy nút 'Cập nhật ngay' (trong vòng ~5–30 phút).")
except Exception as e:
    print(f"\n⚠️ Chưa đẩy được tự động ({e}).")
    print("   Mở GitHub Desktop -> bấm 'Push origin' là xong.")

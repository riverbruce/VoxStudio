"""Tự cập nhật từ GitHub.
- Đọc version.json trên GitHub, so với bản đang cài.
- Có bản mới -> tải gói code (vài trăm KB), sao lưu code cũ, chép đè CHỈ phần code.
- KHÔNG đụng: voices/, projects/, outputs/, models/, cache/, .venv/, runtime/, settings.json, logs/.
- Nếu requirements.txt đổi -> tự cài thêm thư viện. Xong tự khởi động lại."""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

from .config import ROOT

CODE_ITEMS = ["app", "scripts", "assets", "installer", "main.py", "version.json", "requirements.txt",
              "install.ps1", "install.bat", "run.bat", "VoxStudio.vbs", "publish.bat", "HUONG_DAN.md", ".gitignore"]
_cache = {"t": 0, "remote": None, "err": None}


def local_info() -> dict:
    try:
        return json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
    except Exception:
        return {"version": "0.0.0", "repo": "", "branch": "main"}


def _ver(v: str) -> tuple:
    out = []
    for p in str(v).split("."):
        try:
            out.append(int("".join(ch for ch in p if ch.isdigit()) or 0))
        except ValueError:
            out.append(0)
    return tuple(out + [0] * (3 - len(out)))


def configured() -> bool:
    repo = local_info().get("repo", "")
    return bool(repo) and not repo.startswith("OWNER/")


def _get(url: str, timeout=15) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "VoxStudio-Updater", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def check(force=False) -> dict:
    """{'available': bool, 'local': '1.0.0', 'remote': '1.1.0', 'notes': '...', 'error': None}"""
    loc = local_info()
    res = {"available": False, "local": loc.get("version"), "remote": None, "notes": "", "error": None}
    if not configured():
        res["error"] = "Chưa cấu hình kho cập nhật."
        return res
    if not force and time.time() - _cache["t"] < 600 and _cache["remote"]:
        rem = _cache["remote"]
    else:
        try:
            url = (f"https://raw.githubusercontent.com/{loc['repo']}/{loc.get('branch', 'main')}/version.json"
                   f"?t={int(time.time())}")
            rem = json.loads(_get(url, timeout=8).decode("utf-8"))
            _cache.update(t=time.time(), remote=rem, err=None)
        except Exception as e:
            res["error"] = "Không kiểm tra được cập nhật (mất mạng?)."
            _cache["err"] = str(e)
            return res
    res["remote"] = rem.get("version")
    res["notes"] = rem.get("notes", "")
    res["available"] = _ver(rem.get("version", "0")) > _ver(loc.get("version", "0"))
    return res


def _req_hash() -> str:
    f = ROOT / "requirements.txt"
    return hashlib.md5(f.read_bytes()).hexdigest() if f.exists() else ""


def apply(log=print) -> str:
    """Tải & cài bản mới. Trả về phiên bản mới."""
    loc = local_info()
    repo, branch = loc["repo"], loc.get("branch", "main")
    log("Đang tải bản cập nhật…")
    data = _get(f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}", timeout=120)
    zf = zipfile.ZipFile(io.BytesIO(data))
    top = zf.namelist()[0].split("/")[0]
    tmp = ROOT / "tmp" / f"update_{int(time.time())}"
    tmp.mkdir(parents=True, exist_ok=True)
    zf.extractall(tmp)
    src = tmp / top
    new_info = json.loads((src / "version.json").read_text(encoding="utf-8"))
    if not (src / "app" / "ui.py").exists():
        raise RuntimeError("Gói cập nhật không hợp lệ.")

    old_req = _req_hash()
    backup = ROOT / "runtime" / "backup" / f"v{loc.get('version')}_{int(time.time())}"
    backup.mkdir(parents=True, exist_ok=True)
    log("Đang sao lưu bản cũ…")
    for item in CODE_ITEMS:
        p = ROOT / item
        if p.is_dir():
            shutil.copytree(p, backup / item, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("__pycache__"))
        elif p.exists():
            shutil.copy2(p, backup / item)
    log("Đang cài bản mới…")
    for item in CODE_ITEMS:
        s = src / item
        if not s.exists():
            continue
        d = ROOT / item
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy2(s, d)
    # giữ đúng kho cập nhật của máy này
    try:
        nv = json.loads((ROOT / "version.json").read_text(encoding="utf-8"))
        nv["repo"], nv["branch"] = repo, branch
        (ROOT / "version.json").write_text(json.dumps(nv, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    if _req_hash() != old_req:
        log("Đang cài thêm thư viện cho bản mới…")
        uv = ROOT / "runtime" / "uv" / ("uv.exe" if os.name == "nt" else "uv")
        cmd = ([str(uv), "pip", "install", "--python", sys.executable, "-r", str(ROOT / "requirements.txt")]
               if uv.exists() else [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])
        flags = 0x08000000 if os.name == "nt" else 0
        r = subprocess.run(cmd, capture_output=True, creationflags=flags)
        if r.returncode != 0:
            log("Cảnh báo: cài thư viện chưa xong, app vẫn chạy bằng thư viện cũ.")
    shutil.rmtree(tmp, ignore_errors=True)
    log(f"Đã cập nhật lên {new_info.get('version')}")
    return new_info.get("version")


def restart():
    """Khởi động lại app (dùng sau khi cập nhật). Cửa sổ hiện tại sẽ tự tải lại."""
    exe = sys.executable
    if os.name == "nt":
        pyw = Path(exe).with_name("pythonw.exe")
        if pyw.exists():
            exe = str(pyw)
    flags = (0x00000008 | 0x00000200) if os.name == "nt" else 0   # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([exe, str(ROOT / "main.py"), "--restarted"], cwd=str(ROOT), creationflags=flags,
                     close_fds=True)

    def _bye():
        time.sleep(1.5)
        os._exit(0)
    import threading
    threading.Thread(target=_bye, daemon=True).start()

"""VoxStudio – khởi động app.
- Mở trong cửa sổ riêng (Edge/Chrome chế độ app), không cần mở trình duyệt.
- Chỉ chạy 1 bản: mở lại icon khi app đang chạy -> chỉ mở thêm cửa sổ.
- Tự tắt khi đã đóng hết cửa sổ (và không còn việc đang chạy).
Tham số: --no-browser (không mở cửa sổ), --restarted (khởi động lại sau cập nhật)."""
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import CACHE, LOGS, ROOT, SETTINGS  # noqa: E402  (đặt biến môi trường cache trước khi import thư viện)

HOST = SETTINGS.get("host", "127.0.0.1")
PORT = int(SETTINGS.get("port", 7861))
URL = f"http://{HOST}:{PORT}"


# ---------------------------------------------------------------- log ra file (kể cả khi chạy ẩn bằng pythonw)
class _Null:
    def write(self, s):
        return len(s)

    def flush(self):
        pass


class _Tee:
    def __init__(self, stream, fh):
        self.stream, self.fh = stream or _Null(), fh

    def write(self, s):
        try:
            self.stream.write(s)
        except Exception:
            pass
        try:
            self.fh.write(s)
            self.fh.flush()
        except Exception:
            pass
        return len(s)

    def flush(self):
        try:
            self.stream.flush()
        except Exception:
            pass

    def isatty(self):
        return False

    @property
    def encoding(self):
        return "utf-8"

    def fileno(self):
        raise OSError("no fileno")


_logf = LOGS / "app.log"
try:
    if _logf.exists() and _logf.stat().st_size > 20 * 1024 * 1024:
        shutil.move(str(_logf), str(LOGS / "app.old.log"))
except Exception:
    pass
_fh = open(_logf, "a", encoding="utf-8")
sys.stdout = _Tee(sys.stdout, _fh)
sys.stderr = _Tee(sys.stderr, _fh)


# ---------------------------------------------------------------- cửa sổ app
def server_alive() -> bool:
    try:
        with urllib.request.urlopen(URL + "/config", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def find_browser():
    cands = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    return next((c for c in cands if os.path.exists(c)), None)


def open_window():
    """Mở giao diện trong cửa sổ riêng giống phần mềm (chế độ --app)."""
    exe = find_browser()
    if exe:
        prof = CACHE / "window"
        prof.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen([exe, f"--app={URL}", f"--user-data-dir={prof}", "--window-size=1280,900",
                              "--no-first-run", "--no-default-browser-check"])
            return
        except Exception:
            pass
    webbrowser.open(URL)


def splash(stop: threading.Event):
    """Màn hình chờ nhỏ trong lúc app khởi động."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.overrideredirect(True)
        w, h = 380, 130
        root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")
        root.configure(bg="#1e1b4b")
        tk.Label(root, text="🎙️ VoxStudio", fg="white", bg="#1e1b4b", font=("Segoe UI", 18, "bold")).pack(pady=(22, 4))
        msg = tk.Label(root, text="Đang khởi động…", fg="#c7d2fe", bg="#1e1b4b", font=("Segoe UI", 11))
        msg.pack()
        root.attributes("-topmost", True)

        def poll():
            if stop.is_set():
                root.destroy()
            else:
                root.after(200, poll)
        poll()
        root.after(120000, root.destroy)
        root.mainloop()
    except Exception:
        stop.wait(120)


# ---------------------------------------------------------------- tự tắt khi đóng cửa sổ
def watchdog():
    from app import heartbeat, jobs
    try:
        from app import lora
    except Exception:
        lora = None
    while True:
        time.sleep(15)
        idle = time.time() - heartbeat.last_seen()
        busy = jobs.RUNNER.busy() or (lora is not None and lora.is_busy())
        if idle > 180 and not busy:
            print("[VoxStudio] Không còn cửa sổ nào mở -> tắt app.", flush=True)
            os._exit(0)


def port_free(timeout=20) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex((HOST, PORT)) != 0:
                return True
        time.sleep(0.5)
    return False


if __name__ == "__main__":
    restarted = "--restarted" in sys.argv
    if not restarted and server_alive():
        open_window()          # app đang chạy -> chỉ mở thêm cửa sổ
        sys.exit(0)
    if restarted:
        port_free(30)          # đợi bản cũ tắt hẳn

    stop_splash = threading.Event()
    if "--no-browser" not in sys.argv and not restarted:
        threading.Thread(target=splash, args=(stop_splash,), daemon=True).start()

    from app.ui import CSS, HEAD, build_ui  # noqa: E402
    import gradio as gr

    demo = build_ui()
    demo.queue(default_concurrency_limit=4)
    print(f"\n  VoxStudio đang chạy tại {URL}\n", flush=True)

    def after_start():
        for _ in range(240):
            if server_alive():
                break
            time.sleep(0.5)
        stop_splash.set()
        if "--no-browser" not in sys.argv and not restarted:
            open_window()
        from app import heartbeat
        heartbeat.beat()
        if "--no-browser" not in sys.argv:
            threading.Thread(target=watchdog, daemon=True).start()

    threading.Thread(target=after_start, daemon=True).start()
    demo.launch(server_name=HOST, server_port=PORT, inbrowser=False, allowed_paths=[str(ROOT)],
                theme=gr.themes.Soft(primary_hue="indigo"), css=CSS, head=HEAD, show_error=True,
                favicon_path=str(ROOT / "assets" / "icon.png") if (ROOT / "assets" / "icon.png").exists() else None)

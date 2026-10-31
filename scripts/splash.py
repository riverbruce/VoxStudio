"""Màn hình chờ khi VoxStudio khởi động (chạy ở tiến trình riêng, tự tắt khi app sẵn sàng)."""
import sys
import time
import urllib.request

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7861"
T0 = time.time()


def ready():
    try:
        with urllib.request.urlopen(URL + "/config", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


try:
    import tkinter as tk
except Exception:
    sys.exit(0)

root = tk.Tk()
root.overrideredirect(True)
w, h = 400, 140
root.geometry(f"{w}x{h}+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 2}")
root.configure(bg="#1e1b4b")
root.attributes("-topmost", True)
tk.Label(root, text="VoxStudio", fg="white", bg="#1e1b4b", font=("Segoe UI", 20, "bold")).pack(pady=(24, 4))
msg = tk.Label(root, text="Đang khởi động…", fg="#c7d2fe", bg="#1e1b4b", font=("Segoe UI", 11))
msg.pack()
dots = [0]


def poll():
    if ready() or time.time() - T0 > 180:
        root.destroy()
        return
    dots[0] = (dots[0] + 1) % 4
    msg.config(text="Đang khởi động" + "." * dots[0] + " " * (3 - dots[0]))
    root.after(700, poll)


root.after(700, poll)
root.mainloop()

"""Chuyển lỗi kỹ thuật thành câu dễ hiểu cho người dùng bình thường."""
import re

RULES = [
    (r"out of memory|OutOfMemoryError|CUDA error: out of memory",
     "Card đồ hoạ bị hết bộ nhớ (VRAM).",
     "Đóng game, Chrome, phần mềm dựng video đang mở rồi thử lại. Nếu vẫn bị: giảm 'Độ dài mỗi đoạn' hoặc (khi huấn luyện) chọn Rank 16."),
    (r"No CUDA GPUs|CUDA driver|cuda.*not available|Found no NVIDIA driver",
     "Không tìm thấy card đồ hoạ NVIDIA.",
     "Kiểm tra driver NVIDIA đã cài và cập nhật chưa, rồi mở lại app."),
    (r"ffmpeg lỗi|Invalid data found|could not find codec|moov atom not found|Error opening input",
     "Không đọc được file âm thanh/video này (file hỏng hoặc định dạng lạ).",
     "Thử chuyển file sang WAV hoặc MP3 rồi tải lên lại."),
    (r"PermissionError|being used by another process|WinError 32",
     "File đang bị phần mềm khác mở nên không ghi được.",
     "Đóng file đó trong trình phát nhạc / CapCut / Explorer rồi thử lại."),
    (r"No space left|WinError 112|not enough space",
     "Ổ đĩa đã đầy.", "Dọn bớt ổ đĩa chứa VoxStudio rồi thử lại."),
    (r"FileNotFoundError|No such file|cannot find the path|WinError 3|WinError 2",
     "Không tìm thấy file hoặc thư mục cần dùng.",
     "Có thể file đã bị xoá/di chuyển. Bấm 🔄 để làm mới danh sách rồi thử lại."),
    (r"Chưa có checkpoint|Chưa có kết quả huấn luyện",
     "Giọng này chưa có bản huấn luyện nào hoàn tất.", "Bấm 'Bắt đầu huấn luyện' và đợi tới khi báo ✅ xong."),
    (r"tham chiếu|Tạo tham chiếu",
     None, None),
]


def humanize(err) -> str:
    """Trả về markdown thân thiện. Lỗi đã viết sẵn tiếng Việt thì giữ nguyên."""
    text = f"{type(err).__name__}: {err}" if isinstance(err, BaseException) else str(err)
    for pat, msg, tip in RULES:
        if re.search(pat, text, re.I):
            if msg is None:
                break
            return f"❌ **{msg}**\n\n💡 {tip}"
    raw = str(err) if isinstance(err, BaseException) else text
    if re.search(r"[àáạảãâăđèéêìíòóôơùúưỳý]", raw, re.I):   # thông báo tiếng Việt viết sẵn
        return f"❌ {raw}"
    return (f"❌ **Có lỗi xảy ra.** Hãy thử lại; nếu vẫn bị, gửi file `logs/app.log` cho người hỗ trợ.\n\n"
            f"<span class='hint'>Chi tiết: {raw[:200]}</span>")

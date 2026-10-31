"""Điều khiển cảm xúc / phong cách đọc (Controllable Cloning của VoxCPM2).
VoxCPM2 nhận chỉ dẫn phong cách đặt trong ngoặc đơn ở đầu câu: "(cheerful tone)Văn bản..."
- Chọn 1 cảm xúc cho cả bài
- "Tự động theo nội dung": mỗi đoạn tự chọn cảm xúc theo từ ngữ / dấu câu
- Thẻ trong kịch bản: [buồn] ... [vui] ... [bình thường]  -> đổi cảm xúc từ chỗ đó trở đi
  hoặc [style: whispering, scared] để tự viết chỉ dẫn."""
import re

# key: (nhãn hiển thị, chỉ dẫn tiếng Anh với {i}=mức độ, các tên gọi trong thẻ [..])
STYLES = {
    "natural":   ("🙂 Tự nhiên (giống giọng mẫu)", "", ["tự nhiên", "bình thường", "natural", "normal", "/"]),
    "auto":      ("🪄 Tự động theo nội dung", "", ["tự động", "auto"]),
    "story":     ("📖 Kể chuyện đều, ngang", "{i}calm, neutral storytelling tone, steady and even pace",
                  ["kể chuyện", "kể", "ngang", "đều", "story", "narration"]),
    "warm":      ("🤗 Ấm áp, truyền cảm", "{i}warm, gentle and heartfelt narration", ["ấm", "ấm áp", "truyền cảm", "warm"]),
    "happy":     ("😄 Vui tươi", "{i}cheerful, happy and upbeat tone", ["vui", "vui vẻ", "vui tươi", "happy", "cheerful"]),
    "excited":   ("🤩 Hào hứng, sôi nổi (review, TikTok)", "{i}excited, lively and enthusiastic, energetic pace",
                  ["hào hứng", "sôi nổi", "phấn khích", "excited"]),
    "sad":       ("😢 Buồn, trầm lắng", "{i}sad, soft and slow, melancholic tone", ["buồn", "trầm", "sad"]),
    "serious":   ("📰 Nghiêm túc, đọc tin tức", "{i}serious, formal news-anchor tone, clear articulation",
                  ["nghiêm túc", "tin tức", "serious", "news"]),
    "mystery":   ("🕯️ Bí ẩn, hồi hộp, kinh dị", "{i}mysterious and suspenseful, low and slow, tense tone",
                  ["bí ẩn", "hồi hộp", "kinh dị", "mystery", "suspense", "horror"]),
    "angry":     ("😠 Tức giận, gay gắt", "{i}angry, intense and forceful tone", ["giận", "tức giận", "gay gắt", "angry"]),
    "scared":    ("😨 Sợ hãi, run rẩy", "{i}scared, nervous and trembling voice", ["sợ", "sợ hãi", "scared", "fear"]),
    "whisper":   ("🤫 Thì thầm", "soft whispering voice", ["thì thầm", "thầm", "whisper"]),
    "ads":       ("📣 Quảng cáo, thuyết phục", "{i}confident, persuasive advertising voice, energetic",
                  ["quảng cáo", "bán hàng", "ads", "promo"]),
    "custom":    ("✍️ Tự viết chỉ dẫn...", "", []),
}
INTENSITY = {"Nhẹ": "slightly ", "Vừa": "", "Mạnh": "very "}


def choices():
    return [(v[0], k) for k, v in STYLES.items()]


def instruction(key: str, intensity: str = "Vừa", custom: str = "") -> str:
    if key == "custom":
        return (custom or "").strip().strip("()")
    tpl = STYLES.get(key, ("", "", []))[1]
    return tpl.replace("{i}", INTENSITY.get(intensity, "")).strip()


# ---------------------------------------------------------------- tự động theo nội dung
KW = {
    "sad": r"buồn|khóc|nước mắt|đau lòng|đau khổ|mất đi|qua đời|chia tay|cô đơn|tiếc nuối|xót xa|tuyệt vọng|"
           r"\bsad\b|\bcry|tears|grief|lonely|passed away|heartbroken",
    "happy": r"vui|hạnh phúc|tuyệt vời|chúc mừng|cười|hân hoan|yêu đời|thật tốt|\bhappy\b|wonderful|congrat|laugh|joy",
    "excited": r"wow|trời ơi|không thể tin|siêu|cực kỳ|bất ngờ|đỉnh|quá đã|amazing|incredible|unbelievable|awesome",
    "angry": r"tức giận|giận dữ|câm miệng|đồ khốn|chết tiệt|cút|phẫn nộ|\bangry\b|furious|shut up|damn",
    "scared": r"sợ hãi|run rẩy|hoảng|kinh hoàng|ma quỷ|rùng mình|\bscared\b|terrified|afraid|horrif",
    "mystery": r"bí ẩn|bóng tối|lặng lẽ|bỗng nhiên|đột nhiên|kỳ lạ|nửa đêm|không ai biết|mysterious|darkness|suddenly|"
               r"strange|midnight",
    "serious": r"theo báo cáo|thống kê|chính phủ|quy định|cảnh báo|nghiên cứu cho thấy|according to|report|government|warning",
}


def detect(text: str) -> str:
    """Đoán cảm xúc của 1 đoạn. Trung tính -> "natural" (giữ nguyên chất giọng mẫu, Ultimate Cloning)."""
    t = text.lower()
    scores = {k: len(re.findall(p, t)) for k, p in KW.items()}
    excl = t.count("!")
    if excl >= 2:
        scores["excited"] = scores.get("excited", 0) + 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "natural"
    return best


# ---------------------------------------------------------------- thẻ trong kịch bản
_ALIAS = {}
for _k, (_lbl, _tpl, _names) in STYLES.items():
    for _n in _names:
        _ALIAS[_n] = _k
TAG_RE = re.compile(r"\[\s*(?:(style|cảm xúc|cam xuc|giọng)\s*:\s*([^\]]+)|([^\]\d][^\]]{0,24}))\s*\]", re.I)
MARK = "⟦{}⟧"
MARK_RE = re.compile(r"^⟦([^⟧]*)⟧\s*")


def mark_tags(text: str) -> str:
    """Biến thẻ [buồn] / [style: ...] thành mốc riêng ở đầu đoạn để bộ chia đoạn giữ nguyên."""
    def rep(m):
        if m.group(2):
            return "\n\n" + MARK.format("custom:" + m.group(2).strip()) + " "
        name = m.group(3).strip().lower()
        if name in _ALIAS:
            return "\n\n" + MARK.format(_ALIAS[name]) + " "
        return m.group(0)   # không phải thẻ cảm xúc (VD [1], [Nhạc]) -> giữ nguyên
    return TAG_RE.sub(rep, text)


def strip_mark(text: str):
    """Trả về (thẻ hoặc None, văn bản đã bỏ thẻ)."""
    m = MARK_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def has_tags(text: str) -> bool:
    return any((m.group(2) or (m.group(3) or "").strip().lower() in _ALIAS) for m in TAG_RE.finditer(text))

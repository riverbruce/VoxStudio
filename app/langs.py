"""30 ngôn ngữ VoxCPM2 hỗ trợ.
cps = số ký tự đọc mỗi giây (ước lượng, dùng để kiểm tra lỗi & chia đoạn)
spaced = ngôn ngữ có dấu cách giữa các từ (False -> phụ đề tính theo ký tự)"""

LANGS = {
    "vi": ("Tiếng Việt", "🇻🇳", "vietnamese", 14.5, True),
    "en": ("English – Tiếng Anh", "🇺🇸", "english", 15.0, True),
    "zh": ("中文 – Tiếng Trung", "🇨🇳", "chinese", 5.0, False),
    "ja": ("日本語 – Tiếng Nhật", "🇯🇵", "japanese", 7.5, False),
    "ko": ("한국어 – Tiếng Hàn", "🇰🇷", "korean", 7.0, True),
    "th": ("ไทย – Tiếng Thái", "🇹🇭", "thai", 11.0, False),
    "lo": ("ລາວ – Tiếng Lào", "🇱🇦", "lao", 10.0, False),
    "km": ("ខ្មែរ – Tiếng Khmer", "🇰🇭", "khmer", 10.0, False),
    "my": ("မြန်မာ – Tiếng Miến Điện", "🇲🇲", "burmese", 8.0, False),
    "id": ("Bahasa Indonesia", "🇮🇩", "indonesian", 15.0, True),
    "ms": ("Bahasa Melayu", "🇲🇾", "malay", 15.0, True),
    "tl": ("Tagalog – Philippines", "🇵🇭", "tagalog", 15.0, True),
    "hi": ("हिन्दी – Tiếng Hindi", "🇮🇳", "hindi", 13.0, True),
    "fr": ("Français – Tiếng Pháp", "🇫🇷", "french", 15.0, True),
    "de": ("Deutsch – Tiếng Đức", "🇩🇪", "german", 14.5, True),
    "es": ("Español – Tây Ban Nha", "🇪🇸", "spanish", 15.5, True),
    "pt": ("Português – Bồ Đào Nha", "🇵🇹", "portuguese", 15.0, True),
    "it": ("Italiano – Tiếng Ý", "🇮🇹", "italian", 15.0, True),
    "ru": ("Русский – Tiếng Nga", "🇷🇺", "russian", 14.0, True),
    "pl": ("Polski – Tiếng Ba Lan", "🇵🇱", "polish", 14.0, True),
    "nl": ("Nederlands – Hà Lan", "🇳🇱", "dutch", 14.5, True),
    "da": ("Dansk – Đan Mạch", "🇩🇰", "danish", 14.5, True),
    "sv": ("Svenska – Thụy Điển", "🇸🇪", "swedish", 14.5, True),
    "no": ("Norsk – Na Uy", "🇳🇴", "norwegian", 14.5, True),
    "fi": ("Suomi – Phần Lan", "🇫🇮", "finnish", 13.5, True),
    "el": ("Ελληνικά – Hy Lạp", "🇬🇷", "greek", 14.0, True),
    "tr": ("Türkçe – Thổ Nhĩ Kỳ", "🇹🇷", "turkish", 14.0, True),
    "ar": ("العربية – Ả Rập", "🇸🇦", "arabic", 13.0, True),
    "he": ("עברית – Do Thái", "🇮🇱", "hebrew", 13.0, True),
    "sw": ("Kiswahili", "🇰🇪", "swahili", 14.0, True),
}


def label(code: str) -> str:
    n, f, *_ = LANGS.get(code, (code, "🌐", code, 14.0, True))
    return f"{f} {n}"


def choices() -> list:
    return [(label(c), c) for c in LANGS]


def whisper_name(code: str) -> str:
    return LANGS.get(code, (None, None, None))[2] or None


def cps(code: str) -> float:
    return LANGS.get(code, (0, 0, 0, 14.5))[3]


def spaced(code: str) -> bool:
    return LANGS.get(code, (0, 0, 0, 0, True))[4]

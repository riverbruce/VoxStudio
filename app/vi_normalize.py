"""Chuẩn hoá văn bản tiếng Việt trước khi đọc: số, ngày giờ, %, tiền tệ,
đơn vị, chữ viết tắt, số La Mã sau "chương/phần/tập"..."""
import re

DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
VI_CHARS = "àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"


def is_vietnamese(text: str) -> bool:
    t = text.lower()
    n = sum(1 for c in t if c in VI_CHARS)
    letters = sum(1 for c in t if c.isalpha()) or 1
    return n / letters > 0.03


def _read_triple(n: int, full: bool) -> str:
    """Đọc số 0-999. full=True: đọc cả 'không trăm' / 'linh' (nhóm không đứng đầu)."""
    h, t, u = n // 100, (n // 10) % 10, n % 10
    w = []
    if h > 0 or full:
        w += [DIGITS[h], "trăm"]
    if t == 0:
        if u != 0 and (h > 0 or full):
            w.append("linh")
        if u != 0:
            w.append(DIGITS[u])
    elif t == 1:
        w.append("mười")
        if u == 5:
            w.append("lăm")
        elif u != 0:
            w.append(DIGITS[u])
    else:
        w += [DIGITS[t], "mươi"]
        if u == 1:
            w.append("mốt")
        elif u == 4:
            w.append("tư")
        elif u == 5:
            w.append("lăm")
        elif u != 0:
            w.append(DIGITS[u])
    return " ".join(w)


def read_number(n: int) -> str:
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + read_number(-n)
    if n >= 10 ** 9:
        hi, lo = divmod(n, 10 ** 9)
        s = read_number(hi) + " tỷ"
        if lo:
            s += " " + _read_below_billion(lo, full=True)
        return s
    return _read_below_billion(n, full=False)


def _read_below_billion(n: int, full: bool) -> str:
    units = ["", "nghìn", "triệu"]
    groups = []
    while n > 0 or not groups:
        groups.append(n % 1000)
        n //= 1000
    words = []
    top = len(groups) - 1
    for i in range(top, -1, -1):
        g = groups[i]
        if g == 0:
            continue
        need_full = full or i != top
        words.append(_read_triple(g, need_full))
        if units[i]:
            words.append(units[i])
    return " ".join(words)


def read_digits(s: str) -> str:
    return " ".join(DIGITS[int(c)] for c in s if c.isdigit())


def read_decimal(int_part: str, frac: str) -> str:
    s = read_number(int(int_part)) + " phẩy "
    frac = frac.rstrip("0") or "0"
    if len(frac) <= 2 and not frac.startswith("0"):
        s += read_number(int(frac))
    else:
        s += read_digits(frac)
    return s


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman_to_int(s: str):
    s = s.upper()
    if not re.fullmatch(r"M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})", s) or not s:
        return None
    total = 0
    for i, c in enumerate(s):
        v = ROMAN[c]
        if i + 1 < len(s) and ROMAN[s[i + 1]] > v:
            total -= v
        else:
            total += v
    return total


ABBR = {
    "TP.HCM": "thành phố Hồ Chí Minh", "TP. HCM": "thành phố Hồ Chí Minh", "TPHCM": "thành phố Hồ Chí Minh",
    "HCM": "Hồ Chí Minh", "TP.": "thành phố", "Tp.": "thành phố", "v.v.": "vân vân", "v.v": "vân vân",
    "VN": "Việt Nam", "UBND": "ủy ban nhân dân", "HĐND": "hội đồng nhân dân", "THPT": "trung học phổ thông",
    "THCS": "trung học cơ sở", "ĐH": "đại học", "GS.": "giáo sư", "PGS.": "phó giáo sư", "TS.": "tiến sĩ",
    "ThS.": "thạc sĩ", "BS.": "bác sĩ", "ông/bà": "ông bà", "Q.": "quận", "P.": "phường", "CEO": "xi i âu",
    "AI": "ây ai", "KOL": "cây âu eo", "USD": "đô la Mỹ", "VND": "đồng", "VNĐ": "đồng", "km/h": "ki lô mét trên giờ",
    "&": "và", "Mr.": "mít tơ", "Mrs.": "mi xít", "Dr.": "đốc tơ", "No.": "số",
}

UNITS = {
    "km2": "ki lô mét vuông", "m2": "mét vuông", "m3": "mét khối", "km": "ki lô mét", "cm": "xen ti mét",
    "mm": "mi li mét", "m": "mét", "kg": "ki lô gam", "g": "gam", "mg": "mi li gam", "tấn": "tấn",
    "l": "lít", "ml": "mi li lít", "h": "giờ", "ph": "phút", "s": "giây", "ha": "héc ta",
    "kw": "ki lô oát", "kwh": "ki lô oát giờ", "w": "oát", "v": "vôn", "mb": "mê ga bai", "gb": "gi ga bai",
    "tb": "tê ra bai", "ghz": "gi ga héc", "mhz": "mê ga héc", "hz": "héc", "°c": "độ xê", "°f": "độ ép",
    "fps": "khung hình trên giây", "k": "nghìn", "tr": "triệu", "đ": "đồng", "₫": "đồng", "$": "đô la",
    "%": "phần trăm", "x": "lần",
}

NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"


def _num_to_words(s: str) -> str:
    """'1.234.567,89' -> chữ (định dạng Việt: chấm ngăn nghìn, phẩy thập phân)."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?", s):
        intp, _, frac = s.replace(".", "").partition(",")
    elif re.fullmatch(r"\d+,\d+", s):
        intp, _, frac = s.partition(",")
    elif re.fullmatch(r"\d+\.\d+", s):  # kiểu Anh 3.5
        intp, _, frac = s.partition(".")
    else:
        intp, frac = s, ""
    if len(intp) > 1 and intp.startswith("0"):
        base = read_digits(intp)
    else:
        base = read_number(int(intp))
    if frac:
        frac = frac.rstrip("0") or "0"
        return base + " phẩy " + (read_number(int(frac)) if len(frac) <= 2 and not frac.startswith("0") else read_digits(frac))
    return base


def normalize_vi(text: str) -> str:
    t = text
    # chữ viết tắt (dài trước)
    for k in sorted(ABBR, key=len, reverse=True):
        t = re.sub(r"(?<![\w])" + re.escape(k) + r"(?![\w])", ABBR[k], t)

    # Chương/Phần/Tập + số La Mã
    def _roman(m):
        v = roman_to_int(m.group(2))
        return f"{m.group(1)} {read_number(v)}" if v else m.group(0)
    t = re.sub(r"(?i)\b(chương|phần|tập|quyển|hồi|mục|thế kỷ|thế kỉ|khóa|kỳ)\s+([IVXLCDM]+)\b", _roman, t)

    # ngày tháng năm
    def _date(m):
        d, mo, y = m.group(1), m.group(2), m.group(3)
        pre = t_prefix(m)
        s = f"{'' if pre else 'ngày '}{read_number(int(d))} tháng {read_number(int(mo))}"
        if y:
            s += f" năm {read_number(int(y))}"
        return s
    def t_prefix(m):
        return re.search(r"(?i)ngày\s*$", m.string[max(0, m.start() - 6):m.start()]) is not None
    t = re.sub(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{4}))\b", _date, t)
    t = re.sub(r"(?i)\bngày\s+(\d{1,2})/(\d{1,2})\b", lambda m: f"ngày {read_number(int(m.group(1)))} tháng {read_number(int(m.group(2)))}", t)
    t = re.sub(r"\btháng\s+(\d{1,2})/(\d{4})\b", lambda m: f"tháng {read_number(int(m.group(1)))} năm {read_number(int(m.group(2)))}", t)

    # giờ: 14:30, 7h30, 7h
    t = re.sub(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b",
               lambda m: f"{read_number(int(m.group(1)))} giờ" + (f" {read_number(int(m.group(2)))} phút" if int(m.group(2)) else "")
               + (f" {read_number(int(m.group(3)))} giây" if m.group(3) and int(m.group(3)) else ""), t)
    t = re.sub(r"\b(\d{1,2})h(\d{2})\b", lambda m: f"{read_number(int(m.group(1)))} giờ {read_number(int(m.group(2)))} phút", t)

    # khoảng: 10-20 -> mười đến hai mươi
    t = re.sub(rf"\b({NUM})\s*[-–]\s*({NUM})\b(?=\s*(%|\w))", lambda m: f"{m.group(1)} đến {m.group(2)}", t)
    t = re.sub(r"\b(\d{4})\s*[-–]\s*(\d{4})\b", r"\1 đến \2", t)

    # tiền tệ trước số: $100
    t = re.sub(rf"\$\s?({NUM})", lambda m: f"{_num_to_words(m.group(1))} đô la", t)
    t = re.sub(rf"€\s?({NUM})", lambda m: f"{_num_to_words(m.group(1))} ơ rô", t)

    # số thứ tự: thứ 2 -> thứ hai, thứ 4 -> thứ tư, thứ 1 -> thứ nhất
    t = re.sub(r"\b(thứ|hạng|lần thứ)\s+1\b", r"\1 nhất", t)
    t = re.sub(r"\b(thứ|hạng|lần thứ)\s+4\b", r"\1 tư", t)

    # số + đơn vị
    unit_keys = sorted(UNITS, key=len, reverse=True)
    unit_re = "|".join(re.escape(u) for u in unit_keys)

    def _unit(m):
        return f"{_num_to_words(m.group(1))} {UNITS[m.group(2).lower()]}"
    t = re.sub(rf"\b({NUM})\s?({unit_re})(?![\w])", _unit, t, flags=re.I)

    # số điện thoại / dãy số dài bắt đầu bằng 0 -> đọc từng chữ số
    t = re.sub(r"\b0\d{8,10}\b", lambda m: read_digits(m.group(0)), t)
    # số còn lại
    t = re.sub(rf"\b({NUM})\b", lambda m: _num_to_words(m.group(1)), t)
    t = re.sub(r"(đồng|đô la|mét|gam|giờ|lít|tấn|người)\s*/\s*", r"\1 một ", t)
    # ký hiệu
    t = t.replace("%", " phần trăm").replace("+", " cộng ").replace("=", " bằng ")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


_TN = None


def normalize(text: str, lang: str = "auto") -> str:
    """Chuẩn hoá theo ngôn ngữ đọc: vi -> bộ chuẩn hoá tiếng Việt; zh/en -> bộ của VoxCPM;
    ngôn ngữ khác -> giữ nguyên (VoxCPM2 tự xử lý)."""
    global _TN
    if lang == "vi" or (lang == "auto" and is_vietnamese(text)):
        return normalize_vi(text)
    if lang in ("zh", "en"):
        try:
            if _TN is None:
                from voxcpm.utils.text_normalize import TextNormalizer
                _TN = TextNormalizer()
            return _TN.normalize(text)
        except Exception:
            return text
    return text

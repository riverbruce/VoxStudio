"""Chia văn bản dài thành các đoạn nhỏ an toàn cho TTS.
Mỗi đoạn kết thúc ở ranh giới câu; ghi lại loại khoảng nghỉ phía sau
(sentence / paragraph / chapter) và chương chứa nó."""
import re

CHAPTER_RE = re.compile(
    r"^\s*(#{1,3}\s+.+|(chương|chapter|phần|part|hồi|tập|quyển|episode)\s+[\wIVXLCDM]+[.:\-–]?.{0,80})\s*$",
    re.I,
)
SENT_RE = re.compile(r"(?<=[.!?…])[\"'”’」』)\]]*\s+|(?<=[。！？؟۔।॥။។៕])[\"'”’」』)\]]*\s*|(?<=[;:；：])\s+(?=\S)")


def split_sentences(p: str) -> list:
    parts = [s.strip() for s in SENT_RE.split(p) if s and s.strip()]
    return parts


def _hard_split(s: str, max_chars: int) -> list:
    """Ngôn ngữ không có dấu cách (Trung/Nhật/Thái...): cắt theo số ký tự."""
    return [s[i:i + max_chars] for i in range(0, len(s), max_chars)]


def _split_long(s: str, max_chars: int) -> list:
    """Câu quá dài -> cắt tại dấu phẩy / liên từ / khoảng trắng."""
    if len(s) <= max_chars:
        return [s]
    if " " not in s.strip():
        pieces = re.split(r"(?<=[,，、；;])", s)
        out, cur = [], ""
        for pc in pieces:
            for h in (_hard_split(pc, max_chars) if len(pc) > max_chars else [pc]):
                if len(cur) + len(h) > max_chars and cur:
                    out.append(cur); cur = h
                else:
                    cur += h
        if cur:
            out.append(cur)
        return out
    out, cur = [], ""
    pieces = re.split(r"(?<=[,，、—–])\s+", s)
    for pc in pieces:
        if len(pc) > max_chars:
            words = pc.split()
            buf = ""
            for w in words:
                if len(buf) + len(w) + 1 > max_chars and buf:
                    out.append((cur + " " + buf).strip() if cur else buf); cur = ""; buf = w
                else:
                    buf = (buf + " " + w).strip()
            pc = buf
        if len(cur) + len(pc) + 1 > max_chars and cur:
            out.append(cur.strip()); cur = pc
        else:
            cur = (cur + " " + pc).strip()
    if cur:
        out.append(cur.strip())
    return out


def chunk_text(text: str, max_chars: int = 240, min_chars: int = 40, lang: str = "vi") -> list:
    """Trả về list dict: {text, pause, chapter, chapter_title}.
    max_chars tính cho tiếng Việt; ngôn ngữ khác quy đổi theo tốc độ đọc (giữ ~cùng số giây mỗi đoạn)."""
    from .langs import cps
    ratio = cps(lang) / 14.5
    max_chars = max(20, int(max_chars * ratio))
    min_chars = max(4, int(min_chars * ratio))
    joiner = " " if _spaced(lang) else ""
    paragraphs = re.split(r"\n\s*\n|\n(?=\s*[-–•*]\s)", text.replace("\r", ""))
    chunks = []
    chapter = 0
    chapter_title = ""
    for para in paragraphs:
        lines = [l.strip() for l in para.split("\n") if l.strip()]
        if not lines:
            continue
        # nhận diện tiêu đề chương
        if len(lines) >= 1 and CHAPTER_RE.match(lines[0]) and len(lines[0]) < 120:
            title = lines[0].lstrip("#").strip()
            if chunks:
                chunks[-1]["pause"] = "chapter"
            chapter += 1
            chapter_title = title
            t = title if re.search(r"[.!?:]$", title) else title + "."
            chunks.append({"text": t, "pause": "paragraph", "chapter": chapter, "chapter_title": title})
            lines = lines[1:]
            if not lines:
                continue
        para_text = joiner.join(lines)
        sents = []
        for s in split_sentences(para_text):
            sents.extend(_split_long(s, max_chars))
        cur = ""
        for s in sents:
            if not cur:
                cur = s
            elif len(cur) + 1 + len(s) <= max_chars:
                cur = cur + joiner + s
            else:
                chunks.append({"text": cur, "pause": "sentence", "chapter": chapter, "chapter_title": chapter_title})
                cur = s
        if cur:
            # gộp đoạn cuối quá ngắn vào đoạn trước (cùng đoạn văn)
            if (len(cur) < min_chars and chunks and chunks[-1]["pause"] == "sentence"
                    and chunks[-1]["chapter"] == chapter and len(chunks[-1]["text"]) + len(cur) + 1 <= max_chars * 1.25):
                chunks[-1]["text"] += joiner + cur
            else:
                chunks.append({"text": cur, "pause": "sentence", "chapter": chapter, "chapter_title": chapter_title})
        if chunks:
            chunks[-1]["pause"] = "paragraph"
    if chunks:
        chunks[-1]["pause"] = "end"
    # đảm bảo mỗi đoạn có dấu kết câu -> ngữ điệu tự nhiên hơn
    for c in chunks:
        if re.search(r"[,，、—–]$", c["text"]):
            if c["pause"] == "sentence":
                c["pause"] = "comma"
            continue
        if not re.search(r"[.!?…:;\"”')。！？؟۔।॥။។៕」』]$", c["text"]):
            c["text"] += "." if _spaced(lang) else ("。" if lang in ("zh", "ja") else " ")
    return chunks


def _spaced(lang):
    from .langs import spaced
    return spaced(lang)


def estimate_seconds(text: str, lang: str = "vi") -> float:
    from .langs import cps
    return max(0.6, len(re.sub(r"\s+", " ", text)) / cps(lang))

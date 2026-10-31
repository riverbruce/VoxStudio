"""Đọc văn bản kịch bản từ nhiều định dạng: txt, md, srt, vtt, ass, json, jsonl,
csv, tsv, docx, pdf, epub, html, rtf, xml, yaml, lrc, sbv.
Kết quả: chuỗi văn bản, đoạn văn cách nhau bằng dòng trống."""
import csv
import io
import json
import re
from pathlib import Path

TEXT_KEYS = ["text", "content", "line", "lines", "dialogue", "narration", "script", "sentence",
             "transcript", "caption", "subtitle", "body", "paragraph", "voiceover", "vo", "noi_dung",
             "noidung", "loi_thoai", "kich_ban", "cau"]
SKIP_KEYS = {"id", "start", "end", "time", "timestamp", "speaker", "name", "url", "image", "duration",
             "index", "type", "style", "voice", "emotion"}


def read_bytes_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16"):
        try:
            t = raw.decode(enc)
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                raise UnicodeError
            return t
        except UnicodeError:
            continue
    try:
        import chardet
        enc = chardet.detect(raw[:200000]).get("encoding") or "cp1258"
        return raw.decode(enc, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


TAG_RE = re.compile(r"<[^>]+>")


def _clean_sub(t: str) -> str:
    t = TAG_RE.sub("", t)
    t = re.sub(r"\{\\[^}]*\}", "", t)      # thẻ ASS
    t = t.replace("\\N", " ").replace("\\n", " ")
    return re.sub(r"\s+", " ", t).strip()


def _join_cues(cues: list) -> str:
    """Ghép các cue phụ đề: cue kết thúc bằng dấu câu -> giữ, nếu không thì nối liền.
    Khoảng cách lớn giữa các cue (>2s) -> xuống đoạn."""
    out, para = [], []
    prev_end = None
    for start, end, text in cues:
        if not text:
            continue
        if prev_end is not None and start is not None and start - prev_end > 2.0 and para:
            out.append(" ".join(para)); para = []
        para.append(text)
        prev_end = end
    if para:
        out.append(" ".join(para))
    return "\n\n".join(out)


def _ts(s: str):
    s = s.strip().replace(",", ".")
    m = re.match(r"(?:(\d+):)?(\d+):(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    h = int(m.group(1) or 0)
    return h * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def parse_srt_vtt(t: str) -> list:
    cues = []
    blocks = re.split(r"\n\s*\n", t.replace("\r", ""))
    for b in blocks:
        lines = [l for l in b.split("\n") if l.strip()]
        if not lines:
            continue
        ti = next((i for i, l in enumerate(lines) if "-->" in l), None)
        if ti is None:
            continue
        a, _, z = lines[ti].partition("-->")
        txt = _clean_sub(" ".join(lines[ti + 1:]))
        cues.append((_ts(a), _ts(z.split()[0] if z.split() else z), txt))
    return cues


def parse_ass(t: str) -> list:
    cues = []
    fmt = None
    for line in t.splitlines():
        if line.lower().startswith("format:") and fmt is None and "text" in line.lower():
            fmt = [x.strip().lower() for x in line.split(":", 1)[1].split(",")]
        if line.startswith("Dialogue:"):
            parts = line.split(":", 1)[1].split(",", (len(fmt) - 1) if fmt else 9)
            f = fmt or ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]
            d = dict(zip(f, parts))
            cues.append((_ts(d.get("start", "")), _ts(d.get("end", "")), _clean_sub(d.get("text", ""))))
    return cues


def parse_sbv(t: str) -> list:
    cues = []
    for b in re.split(r"\n\s*\n", t.replace("\r", "")):
        lines = b.strip().split("\n")
        if len(lines) >= 2 and "," in lines[0]:
            a, z = lines[0].split(",", 1)
            cues.append((_ts(a), _ts(z), _clean_sub(" ".join(lines[1:]))))
    return cues


def parse_lrc(t: str) -> str:
    return "\n".join(_clean_sub(re.sub(r"\[[^\]]*\]", "", l)) for l in t.splitlines()
                     if re.sub(r"\[[^\]]*\]", "", l).strip())


def collect_json_text(obj, out: list, key_hint=None):
    if isinstance(obj, str):
        if key_hint is None or key_hint.lower() not in SKIP_KEYS:
            s = obj.strip()
            if s and not re.fullmatch(r"[\w\-./:]+\.(png|jpg|mp3|wav|mp4|json)", s, re.I):
                out.append(s)
    elif isinstance(obj, list):
        for v in obj:
            collect_json_text(v, out, key_hint)
    elif isinstance(obj, dict):
        keys = {k.lower(): k for k in obj.keys()}
        hits = [keys[k] for k in TEXT_KEYS if k in keys]
        if hits:
            for k in hits:
                collect_json_text(obj[k], out, None)
            # đi tiếp vào các nhánh lồng nhau (scenes, chapters, ...)
            for k, v in obj.items():
                if k not in hits and isinstance(v, (list, dict)):
                    collect_json_text(v, out, k)
        else:
            for k, v in obj.items():
                if k.lower() in SKIP_KEYS:
                    continue
                if isinstance(v, str) and len(v) < 25 and k.lower() in ("title", "heading"):
                    out.append(v.strip())
                else:
                    collect_json_text(v, out, k)


def parse_json(t: str, jsonl=False) -> str:
    out = []
    if jsonl:
        for line in t.splitlines():
            if line.strip():
                try:
                    collect_json_text(json.loads(line), out)
                except Exception:
                    pass
    else:
        collect_json_text(json.loads(t), out)
    return "\n\n".join(out)


def parse_csv(t: str, delim=None) -> str:
    sample = t[:5000]
    if delim is None:
        try:
            delim = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except Exception:
            delim = ","
    rows = list(csv.reader(io.StringIO(t), delimiter=delim))
    if not rows:
        return ""
    header = [h.strip().lower() for h in rows[0]]
    col = next((header.index(k) for k in TEXT_KEYS if k in header), None)
    if col is not None:
        return "\n\n".join(r[col].strip() for r in rows[1:] if len(r) > col and r[col].strip())
    # không có cột tên chuẩn -> chọn cột có tổng độ dài chữ lớn nhất
    ncol = max(len(r) for r in rows)
    lens = [sum(len(r[i]) for r in rows if len(r) > i) for i in range(ncol)]
    col = int(max(range(ncol), key=lambda i: lens[i]))
    return "\n\n".join(r[col].strip() for r in rows if len(r) > col and r[col].strip())


def parse_html(t: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(t, "html.parser")
        for s in soup(["script", "style", "nav", "footer", "header"]):
            s.decompose()
        blocks = [b.get_text(" ", strip=True) for b in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "blockquote"])]
        blocks = [b for b in blocks if b]
        return "\n\n".join(blocks) if blocks else soup.get_text("\n", strip=True)
    except Exception:
        return TAG_RE.sub(" ", t)


def parse_docx(path: Path) -> str:
    import docx
    d = docx.Document(str(path))
    parts = [p.text.strip() for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" ".join(dict.fromkeys(cells)))
    return "\n\n".join(parts)


def parse_pdf(path: Path) -> str:
    from pypdf import PdfReader
    r = PdfReader(str(path))
    pages = [(p.extract_text() or "") for p in r.pages]
    t = "\n".join(pages)
    # nối các dòng bị ngắt giữa câu trong PDF
    t = re.sub(r"(?<![.!?:;。…\"”])\n(?!\n)", " ", t)
    return t


def parse_epub(path: Path) -> str:
    import ebooklib
    from ebooklib import epub
    book = epub.read_epub(str(path))
    out = []
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        out.append(parse_html(item.get_content().decode("utf-8", "ignore")))
    return "\n\n".join(o for o in out if o.strip())


def parse_rtf(t: str) -> str:
    t = re.sub(r"\\par[d]?", "\n", t)
    t = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", "ignore"), t)
    t = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), t)
    t = re.sub(r"\\[a-z]+-?\d* ?", "", t)
    return re.sub(r"[{}]", "", t)


def parse_md(t: str) -> str:
    t = re.sub(r"```.*?```", "", t, flags=re.S)
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", t)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = re.sub(r"^\s*[-*+]\s+", "", t, flags=re.M)
    t = re.sub(r"[*_`>]+", "", t)
    return t  # giữ "#" để nhận diện chương


def read_script(path) -> str:
    """Trả về văn bản sạch từ file kịch bản bất kỳ."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".docx":
        text = parse_docx(path)
    elif ext == ".pdf":
        text = parse_pdf(path)
    elif ext == ".epub":
        text = parse_epub(path)
    else:
        t = read_bytes_text(path)
        if ext in (".srt", ".vtt"):
            text = _join_cues(parse_srt_vtt(t))
        elif ext in (".ass", ".ssa"):
            text = _join_cues(parse_ass(t))
        elif ext == ".sbv":
            text = _join_cues(parse_sbv(t))
        elif ext == ".lrc":
            text = parse_lrc(t)
        elif ext == ".json":
            try:
                text = parse_json(t)
            except json.JSONDecodeError:
                text = parse_json(t, jsonl=True)
        elif ext == ".jsonl":
            text = parse_json(t, jsonl=True)
        elif ext in (".csv", ".tsv"):
            text = parse_csv(t, "\t" if ext == ".tsv" else None)
        elif ext in (".html", ".htm", ".xml"):
            text = parse_html(t)
        elif ext == ".rtf":
            text = parse_rtf(t)
        elif ext == ".md":
            text = parse_md(t)
        elif ext in (".yaml", ".yml"):
            try:
                import yaml
                out = []
                collect_json_text(yaml.safe_load(t), out)
                text = "\n\n".join(out)
            except Exception:
                text = t
        else:
            text = t
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

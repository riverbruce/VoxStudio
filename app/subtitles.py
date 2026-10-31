"""Tạo phụ đề SRT khớp với audio đã sinh.
- Tuỳ chỉnh: số từ mỗi dòng (hoặc số ký tự với tiếng Trung/Nhật/Thái...), số dòng mỗi khung,
  thời lượng tối đa mỗi khung, bỏ dấu câu cuối dòng.
- Căn thời gian theo tiếng nói thật trong từng đoạn (bỏ qua chỗ lặng), không chia đều máy móc."""
import re
from pathlib import Path

import numpy as np

from . import audio_utils as au

END_RE = re.compile(r"[.!?…。！？؟۔।॥။។៕]['\"”’」』)]*$")
COMMA_RE = re.compile(r"[,，、;；:：]['\"”’)]*$")

DEFAULT_SUB = {"per_line": 8, "lines": 1, "max_dur": 5.0, "strip_punct": False}


def voiced_curve(x: np.ndarray, sr: int) -> np.ndarray:
    """Đường tích luỹ (0..1) của các khung có tiếng nói, mỗi khung 10ms."""
    db = au.frame_rms_db(x, sr)
    if len(db) < 2:
        return np.array([0.0, 1.0])
    voiced = (db > db.max() - 35).astype(np.float32)
    cum = np.cumsum(voiced)
    return cum / max(cum[-1], 1.0)


def _time_at(st, en, curve, frac):
    if curve is None or len(curve) < 2:
        return st + (en - st) * frac
    idx = int(np.searchsorted(curve, min(max(frac, 0.0), 1.0)))
    return min(en, st + idx * 0.010)


def _tokens(text: str, spaced: bool) -> list:
    if spaced:
        return text.split()
    # gom dấu câu vào ký tự trước đó
    toks = []
    for ch in text:
        if ch.isspace():
            continue
        if toks and re.match(r"[^\w]", ch):
            toks[-1] += ch
        else:
            toks.append(ch)
    return toks


def _lines(tokens: list, per_line: int, spaced: bool) -> list:
    """Chia token thành dòng phụ đề:
    - tách thành cụm theo dấu câu (phẩy, chấm...) để không ngắt giữa ý
    - cụm dài hơn giới hạn -> chia ĐỀU thành nhiều dòng (tránh dòng cuối 1 chữ lẻ loi)
    - cụm ngắn liền nhau được gộp chung dòng nếu vừa, nhưng không gộp qua dấu kết câu"""
    phrases, cur = [], []
    for t in tokens:
        cur.append(t)
        if END_RE.search(t) or COMMA_RE.search(t):
            phrases.append(cur); cur = []
    if cur:
        phrases.append(cur)
    lines = []
    for ph in phrases:
        if len(ph) > per_line:
            k = -(-len(ph) // per_line)
            size = -(-len(ph) // k)
            parts = [ph[i:i + size] for i in range(0, len(ph), size)]
        else:
            parts = [ph]
        for part in parts:
            if lines and not END_RE.search(lines[-1][-1]) and len(lines[-1]) + len(part) <= per_line \
                    and part is parts[0]:
                lines[-1] = lines[-1] + part
            else:
                lines.append(list(part))
    j = " " if spaced else ""
    return [j.join(l) for l in lines]


def _clean(line: str, strip: bool) -> str:
    if strip:
        line = re.sub(r"[.,，、;；:：。!！?？…]+$", "", line).strip()
    return line


def build_cues(timings: list, spaced: bool, per_line=8, lines=1, max_dur=5.0, strip_punct=False,
               speed=1.0) -> list:
    """timings: [(start, end, text, curve)] theo giây trên audio trước khi đổi tốc độ."""
    cues = []
    for st, en, text, curve in timings:
        lns = _lines(_tokens(text, spaced), max(1, int(per_line)), spaced)
        total = sum(len(l) for l in lns) or 1
        # nhóm dòng thành khung
        groups, cur = [], []
        for l in lns:
            cur.append(l)
            if len(cur) >= lines or END_RE.search(l):
                groups.append(cur); cur = []
        if cur:
            groups.append(cur)
        pos = 0
        for g in groups:
            glen = sum(len(l) for l in g)
            a = _time_at(st, en, curve, pos / total)
            b = _time_at(st, en, curve, (pos + glen) / total)
            # khung quá dài -> tách từng dòng
            if b - a > max_dur and len(g) > 1:
                p2 = pos
                for l in g:
                    a2 = _time_at(st, en, curve, p2 / total)
                    b2 = _time_at(st, en, curve, (p2 + len(l)) / total)
                    cues.append([a2, b2, _clean(l, strip_punct)])
                    p2 += len(l)
            else:
                cues.append([a, b, "\n".join(_clean(l, strip_punct) for l in g)])
            pos += glen
    # chỉnh thời gian: không chồng nhau, tối thiểu 0.6s nếu còn chỗ, đổi theo tốc độ
    for i, c in enumerate(cues):
        nxt = cues[i + 1][0] if i + 1 < len(cues) else c[1] + 1.0
        if c[1] - c[0] < 0.6:
            c[1] = min(c[0] + 0.6, nxt - 0.02)
        c[1] = min(c[1], nxt - 0.01) if nxt > c[0] else c[1]
    return [(a / speed, b / speed, t) for a, b, t in cues if t.strip()]


def fmt_ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(int(round(t * 1000)), 3600000)
    m, rem = divmod(rem, 60000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues: list, path) -> Path:
    out = [f"{i}\n{fmt_ts(a)} --> {fmt_ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)]
    Path(path).write_text("\n".join(out), encoding="utf-8")
    return Path(path)

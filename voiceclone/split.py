"""长文本自动分段：先按自然段，超长段再按句末标点，目标 150–250 字，不在句中切断。"""

import re

MAX_CHARS = 250
TARGET_MIN = 150

# 句末标点（含后置引号 / 括号），切在标点之后
_SENTENCE_END = re.compile(r'(?<=[。！？!?；;])(?=["”』」）)\s]*)')


def _split_sentences(text):
    parts = [p for p in _SENTENCE_END.split(text) if p.strip()]
    return parts or [text]


def _hard_wrap(chunk):
    """单句就超过 250 字时的兜底：按逗号类停顿切，再不行才按长度硬切。"""
    if len(chunk) <= MAX_CHARS:
        return [chunk]
    pieces = [p for p in re.split(r'(?<=[，,、：:—])', chunk) if p]
    out, buf = [], ""
    for p in pieces:
        if len(p) > MAX_CHARS:
            if buf:
                out.append(buf)
                buf = ""
            for i in range(0, len(p), MAX_CHARS):
                out.append(p[i:i + MAX_CHARS])
            continue
        if len(buf) + len(p) > MAX_CHARS:
            out.append(buf)
            buf = p
        else:
            buf += p
    if buf:
        out.append(buf)
    return out


def split_text(text, max_chars=MAX_CHARS, target_min=TARGET_MIN):
    """返回分段列表。总长不超过 max_chars 时原样返回单段。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    segments = []
    for paragraph in re.split(r'\n\s*\n|\n', text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(paragraph) <= max_chars:
            segments.append(paragraph)
            continue
        # 段落超长：按句子重新聚成 150–250 字的块
        buf = ""
        for sentence in _split_sentences(paragraph):
            for piece in _hard_wrap(sentence.strip()):
                if not piece:
                    continue
                if len(buf) + len(piece) > max_chars:
                    if buf:
                        segments.append(buf)
                    buf = piece
                else:
                    buf += piece
                    if len(buf) >= target_min and len(buf) + 20 > max_chars:
                        segments.append(buf)
                        buf = ""
        if buf:
            segments.append(buf)

    # 把过短的尾段并回上一段（仍不超上限时）
    merged = []
    for seg in segments:
        if merged and len(seg) < 40 and len(merged[-1]) + len(seg) <= max_chars:
            merged[-1] += seg
        else:
            merged.append(seg)
    return merged

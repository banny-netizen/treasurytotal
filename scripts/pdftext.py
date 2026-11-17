"""PDF에서 글자만 뽑는다. 표준 라이브러리만 쓴다.

워드에서 내보낸 PDF처럼 글자가 문자열 그대로 들어 있는 경우를 대상으로 한다.
글꼴별 코드표(ToUnicode)가 있으면 16진 문자열도 가능한 범위에서 풀어 준다.
"""
from __future__ import annotations

import re
import zlib

_STREAM = re.compile(rb"stream\r?\n")
_TOKEN = re.compile(
    rb"\((?:\\.|[^\\()])*(?:\((?:\\.|[^\\()])*\)(?:\\.|[^\\()])*)*\)"   # (문자열) — 괄호 한 겹까지
    rb"|<[0-9A-Fa-f\s]*>"                                                # <16진>
    rb"|\[|\]"
    rb"|-?\d*\.?\d+"
    rb"|[A-Za-z'\"*]+"
)
_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f",
            b"(": b"(", b")": b")", b"\\": b"\\"}


def _inflate(raw: bytes) -> bytes | None:
    for chunk in (raw, raw.rstrip(b"\r\n")):
        try:
            return zlib.decompress(chunk)
        except zlib.error:
            try:
                return zlib.decompressobj().decompress(chunk)
            except zlib.error:
                continue
    return None


def streams(data: bytes, limit: int = 60_000_000):
    """압축을 푼 스트림을 차례로 돌려준다. 풀리지 않는 것은 건너뛴다."""
    total = 0
    for match in _STREAM.finditer(data):
        start = match.end()
        end = data.find(b"endstream", start)
        if end < 0:
            continue
        body = _inflate(data[start:end])
        if body is None:
            continue
        total += len(body)
        if total > limit:
            return
        yield body


def _unescape(raw: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(raw):
        ch = raw[i:i + 1]
        if ch == b"\\" and i + 1 < len(raw):
            nxt = raw[i + 1:i + 2]
            if nxt in _ESCAPES:
                out += _ESCAPES[nxt]
                i += 2
                continue
            if nxt.isdigit():
                j = i + 1
                while j < len(raw) and j < i + 4 and raw[j:j + 1].isdigit():
                    j += 1
                out.append(int(raw[i + 1:j], 8) & 0xFF)
                i = j
                continue
            if nxt in (b"\n", b"\r"):
                i += 2
                continue
            i += 1
            continue
        out += ch
        i += 1
    return bytes(out)


def _cmap(body: bytes) -> dict[int, str]:
    table: dict[int, str] = {}
    for block in re.findall(rb"beginbfchar(.*?)endbfchar", body, re.S):
        for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            try:
                table[int(src, 16)] = bytes.fromhex(dst.decode()).decode("utf-16-be", "replace")
            except ValueError:
                continue
    for block in re.findall(rb"beginbfrange(.*?)endbfrange", body, re.S):
        for lo, hi, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            first, last, base = int(lo, 16), int(hi, 16), int(dst, 16)
            if last - first > 2000:
                continue
            for offset in range(last - first + 1):
                table[first + offset] = chr(base + offset)
    return table


def _hex_text(raw: bytes, cmap: dict[int, str]) -> str:
    digits = re.sub(rb"\s", b"", raw)
    if len(digits) % 2:
        digits += b"0"
    data = bytes.fromhex(digits.decode())
    if cmap and len(data) % 2 == 0:
        return "".join(cmap.get(int.from_bytes(data[i:i + 2], "big"), "") for i in range(0, len(data), 2))
    return data.decode("latin-1")


def page_text(body: bytes, cmap: dict[int, str]) -> str:
    """내용 스트림 하나에서 글자를 뽑는다."""
    if b"BT" not in body:
        return ""
    out: list[str] = []
    pending: list[str] = []
    numbers: list[float] = []
    in_array = False
    for token in _TOKEN.findall(body):
        first = token[:1]
        if first == b"(":
            pending.append(_unescape(token[1:-1]).decode("cp1252", "replace"))
        elif first == b"<":
            pending.append(_hex_text(token[1:-1], cmap))
        elif first == b"[":
            in_array = True
        elif first == b"]":
            in_array = False
        elif first.isdigit() or first in (b"-", b"."):
            try:
                value = float(token)
            except ValueError:
                continue
            if in_array:
                if value < -180:        # 글자 사이를 크게 띄운 곳은 빈칸으로 본다
                    pending.append(" ")
            else:
                numbers.append(value)
        else:
            if token in (b"Tj", b"TJ", b"'", b'"'):
                out.append("".join(pending))
                if token in (b"'", b'"'):
                    out.append("\n")
            elif token in (b"Td", b"TD"):
                if len(numbers) >= 2 and abs(numbers[-1]) > 0.5:
                    out.append("\n")
                elif len(numbers) >= 2 and numbers[-2] > 1.5:
                    out.append(" ")
            elif token in (b"T*", b"ET", b"Tm"):
                out.append("\n")
            pending = []
            numbers = []
    return "".join(out)


def extract(data: bytes) -> str:
    """PDF 전체에서 글자를 뽑아 한 문자열로."""
    bodies = list(streams(data))
    cmap: dict[int, str] = {}
    for body in bodies:
        if b"beginbfchar" in body or b"beginbfrange" in body:
            cmap.update(_cmap(body))
    parts = [page_text(body, cmap) for body in bodies]
    text = "\n".join(part for part in parts if part.strip())
    return re.sub(r"[ \t]+", " ", text)

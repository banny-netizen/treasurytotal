"""허용 목록에 있는 주소의 응답 모양을 확인한다. 새 출처를 붙이기 전 확인용.

probe_urls.txt 한 줄에 "<방식> <주소>" 를 적는다. 방식을 생략하면 full.
  full    본문 그대로 (최대 300KB)
  head    앞 4,000자 + 끝 1,000자
  tables  HTML 표만 (표마다 앞 70행)
  links   HTML 링크 목록만
  pdf     PDF에서 뽑은 글자 중 확인에 필요한 줄과 그 앞뒤 두 줄
  text    HTML에서 태그를 뗀 글자 (주소 끝에 "#@표시어" 를 붙이면 그 말이 처음 나오는 곳부터 14,000자)
  dbn     DBnomics 응답에서 시리즈별 이름과 마지막 세 값만
결과는 probe_out/ 에 쓴다. probe/ 브랜치에서만 쓰고 main 에는 두지 않는다.
"""
from __future__ import annotations

import json
import re
import sys
import time
from urllib.parse import urlsplit

import common
import pdftext

OUT = common.ROOT / "probe_out"
FULL_LIMIT = 300_000
MODES = {"full", "head", "tables", "links", "pdf", "text", "dbn"}
PDF_KEYS = re.compile(r"P/E|forward 12|closing price|year average", re.I)


def render(mode: str, body: bytes, marker: str = "") -> str:
    if mode == "pdf" or body[:5] == b"%PDF-":
        text = pdftext.extract(body)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        keep: set[int] = set()
        hits = [i for i, line in enumerate(lines) if re.search(r"P/E ratio|closing price", line, re.I)]
        for i in hits[:14]:
            keep.update(range(max(0, i - 2), min(len(lines), i + 4)))
        return (f"[pdf] 글자 {len(text)}자, 줄 {len(lines)}개, 해당 줄 {len(hits)}개\n"
                + "\n".join(f"{i}: {lines[i][:200]}" for i in sorted(keep)))
    text = common.decode_text(body)
    if mode == "dbn":
        docs = json.loads(text)["series"]["docs"]
        return f"시리즈 {len(docs)}개\n" + "\n".join(
            f"{d.get('series_code')} | {d.get('series_name', '')[:110]} | "
            f"{d.get('period', [])[-3:]} | {d.get('value', [])[-3:]}" for d in docs)
    if mode == "text":
        plain = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", text)
        plain = re.sub(r"(?s)<[^>]+>", "\n", plain)
        plain = "\n".join(line.strip() for line in plain.splitlines() if line.strip())
        start = plain.find(marker) if marker else 0
        return plain[max(start, 0):max(start, 0) + 14000]
    if mode == "tables":
        out = []
        for number, (caption, rows) in enumerate(common.html_tables(text, with_captions=True), 1):
            out.append(f"--- 표 {number}: {len(rows)}행 | {caption[:160]}")
            for row in rows[:70]:
                out.append(" | ".join(cell[0][:60] for cell in row))
        return "\n".join(out)
    if mode == "links":
        return "\n".join(f"{label[:90]} -> {href[:200]}" for label, href in common.html_links(text))
    if mode == "head":
        if len(text) <= 5200:
            return text
        return text[:4000] + "\n…(중략)…\n" + text[-1000:]
    if len(text) > FULL_LIMIT:
        return text[:FULL_LIMIT] + f"\n…(이하 생략, 전체 {len(text)}자)"
    return text


def probe(number: int, mode: str, url: str) -> str:
    header = [f"URL: {url}", f"MODE: {mode}"]
    started = time.time()
    url, _, marker = url.partition("#@")
    try:
        body = common.fetch(url, retries=2)
        header.append(f"OK: {len(body)}바이트, {time.time() - started:.1f}초")
        content = render(mode, body, marker)
    except Exception as exc:
        header.append(f"FAIL: {type(exc).__name__}: {exc}")
        content = ""
    host = (urlsplit(url).hostname or "x").replace(".", "_")
    OUT.mkdir(exist_ok=True)
    (OUT / f"{number:02d}_{host}.txt").write_text("\n".join(header) + "\n\n" + content + "\n", encoding="utf-8")
    return header[-1]


def main() -> int:
    path = common.ROOT / "probe_urls.txt"
    if not path.exists():
        print("probe_urls.txt 가 없습니다.")
        return 0
    number = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        mode, url = (parts[0], parts[1]) if len(parts) == 2 and parts[0] in MODES else ("full", line)
        number += 1
        print(f"{number:02d} {mode} {urlsplit(url).hostname}: {probe(number, mode, url)}")
        time.sleep(1.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())

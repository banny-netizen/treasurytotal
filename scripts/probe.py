"""허용 목록에 있는 주소의 응답 모양을 확인한다. 새 출처를 붙이기 전 확인용.

probe_urls.txt 한 줄에 "<방식> <주소>" 를 적는다. 방식을 생략하면 full.
  full    본문 그대로 (최대 300KB)
  head    앞 4,000자 + 끝 1,000자
  tables  HTML 표만 (표마다 앞 70행)
  links   HTML 링크 목록만
  pdf     PDF에서 뽑은 글자 중 확인에 필요한 줄만
결과는 probe_out/ 에 쓴다. probe/ 브랜치에서만 쓰고 main 에는 두지 않는다.
"""
from __future__ import annotations

import re
import sys
import time
from urllib.parse import urlsplit

import common
import pdftext

OUT = common.ROOT / "probe_out"
FULL_LIMIT = 300_000
MODES = {"full", "head", "tables", "links", "pdf"}
PDF_KEYS = re.compile(r"P/E|forward 12|closing price|year average", re.I)


def render(mode: str, body: bytes) -> str:
    if mode == "pdf" or body[:5] == b"%PDF-":
        text = pdftext.extract(body)
        lines = [line.strip() for line in text.splitlines() if PDF_KEYS.search(line)]
        return (f"[pdf] 글자 {len(text)}자, 해당 줄 {len(lines)}개\n"
                + "\n".join(line[:400] for line in lines[:40]))
    text = common.decode_text(body)
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
    try:
        body = common.fetch(url, retries=2)
        header.append(f"OK: {len(body)}바이트, {time.time() - started:.1f}초")
        content = render(mode, body)
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

"""머니마켓 마감 보고서 목록 — 트래디션 서울 게시판.

보고서 본문은 받지 않는다. 날짜와 원문 주소만 모으고, 화면은 원문 사이트의 파일을 그대로 연다.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin, urlsplit

import common

NAME = "머니마켓 마감시황"
OUTPUTS = ["mm.json"]
BOARD = "https://www.traditionkorea.com/marketData.html"
KEEP = 30


def parse(html: str) -> list[dict]:
    """게시판 표 → [{date, url}] (최근 순). 제목이 'Daily Report (YYYYMMDD)' 인 행만."""
    reports = {}
    for rows in common.html_tables(html):
        for row in rows:
            title = next((text for text, _ in row if "Daily Report" in text), None)
            link = next((href for _, href in row if href and href.lower().endswith(".pdf")), None)
            stamp = re.search(r"\((\d{4})(\d{2})(\d{2})\)", title or "")
            if not stamp or not link:
                continue
            url = urljoin(BOARD, link)
            if urlsplit(url).hostname != urlsplit(BOARD).hostname or not url.startswith("https://"):
                continue
            day = "-".join(stamp.groups())
            reports[day] = {"date": day, "url": url}
    return [reports[day] for day in sorted(reports, reverse=True)]


def collect(today: date, previous: dict) -> dict:
    new = parse(common.fetch_text(BOARD))
    if not new:
        raise ValueError("게시판에서 보고서 목록을 찾지 못함")
    merged = {r["date"]: r for r in (previous.get("mm.json") or {}).get("reports", [])}
    merged.update({r["date"]: r for r in new})
    reports = [merged[day] for day in sorted(merged, reverse=True)][:KEEP]
    return {"files": {"mm.json": {"board": BOARD, "reports": reports}},
            "latest": reports[0]["date"], "warnings": []}

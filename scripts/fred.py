"""FRED 시계열 내려받기 (키 없이 받을 수 있는 CSV 주소).

한 번에 한 시리즈만 받는다. 여러 시리즈를 한 주소로 받으면 주기가 섞일 때 압축 파일이 온다.
"""
from __future__ import annotations

import time

import common

URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}{since}"
PAUSE = 0.6      # 연속 호출 사이 간격(초)


def parse(text: str, sid: str) -> list:
    """CSV → [[날짜, 값]] (오름차순, 빈 값 제외)."""
    rows = []
    for row in common.csv_rows(text):
        day = common.iso_day(row.get("observation_date") or row.get("DATE"))
        value = common.to_float(row.get(sid))
        if day and value is not None:
            rows.append([day, value])
    if not rows and sid not in text.splitlines()[0]:
        raise ValueError(f"FRED 응답에 {sid} 열이 없음")
    return sorted(rows)


def series(sid: str, since: str | None = None) -> list:
    text = common.fetch_text(URL.format(sid=sid, since=f"&cosd={since}" if since else ""))
    time.sleep(PAUSE)
    return [row for row in parse(text, sid) if since is None or row[0] >= since]

"""자동차대출 90일 이상 연체율과 잔액 — 뉴욕 연은 분기 가계신용 보고서.

보고서 인터랙티브 화면이 쓰는 자료 파일(main.js)에 배열로 들어 있다.
"""
from __future__ import annotations

import re
from datetime import date

import common

NAME = "자동차대출 연체율"
OUTPUTS = ["delinq.json"]
URL = "https://www.newyorkfed.org/medialibrary/interactives/householdcredit/js/main.js"


def js_array(text: str, name: str) -> list[str]:
    match = re.search(r"\b" + re.escape(name) + r"\s*=\s*\[(.*?)\]", text, re.S)
    if not match:
        raise ValueError(f"자료 파일에 {name} 배열이 없음")
    return [item.strip().strip("\"'") for item in match.group(1).split(",") if item.strip()]


def parse(text: str) -> dict:
    quarters = []
    for label in js_array(text, "categoriesInput90Day"):
        match = re.fullmatch(r"(\d{4}):Q([1-4])", label)
        if not match:
            raise ValueError(f"분기 표기 이상: {label}")
        quarters.append(f"{match.group(1)}Q{match.group(2)}")
    rate = [common.to_float(v) for v in js_array(text, "auto2Input")]
    balance = [common.to_float(v) for v in js_array(text, "auto1Input")]
    if not (len(quarters) == len(rate) == len(balance)) or len(quarters) < 40:
        raise ValueError(f"배열 길이 불일치: 분기 {len(quarters)}, 연체율 {len(rate)}, 잔액 {len(balance)}")
    if not all(v is not None and 0 <= v <= 20 for v in rate):
        raise ValueError("연체율 값이 범위를 벗어남")
    return {
        "latest": quarters[-1],
        "series": {
            "auto_d90": {"label": "자동차대출 90일 이상 연체율", "unit": "%",
                         "obs": [[q, v] for q, v in zip(quarters, rate)]},
            "auto_bal": {"label": "자동차대출 잔액", "unit": "조 달러",
                         "obs": [[q, v] for q, v in zip(quarters, balance)]},
        },
    }


def collect(today: date, previous: dict) -> dict:
    data = parse(common.fetch_text(URL))
    return {"files": {"delinq.json": data}, "latest": data["latest"], "warnings": []}

"""미국 경제지표: 물가·통화, 고용, 경기. 전부 FRED에서 받는다(원자료는 BLS·BEA·연준·Census).

ISM PMI, 미시간대 소비자심리처럼 재배포가 제한된 민간 지표는 싣지 않는다.
대신 연준·지역 연은이 공개하는 활동 지수를 쓴다.
"""
from __future__ import annotations

from datetime import date

import fred

NAME = "미국 경제지표"
OUTPUTS = ["macro.json"]
SINCE = "2000-01-01"

# 키, FRED 시리즈, 이름, 단위, 주기, 변환, 원출처
SERIES = [
    ("cpi", "CPIAUCSL", "CPI", "%", "M", "yoy", "BLS"),
    ("cpi_core", "CPILFESL", "근원 CPI", "%", "M", "yoy", "BLS"),
    ("pce", "PCEPI", "PCE 물가", "%", "M", "yoy", "BEA"),
    ("pce_core", "PCEPILFE", "근원 PCE 물가", "%", "M", "yoy", "BEA"),
    ("m2", "M2SL", "M2", "%", "M", "yoy", "연준"),
    ("fed_assets", "WALCL", "연준 총자산", "조 달러", "W", "scale:0.000001", "연준"),
    ("unrate", "UNRATE", "실업률", "%", "M", "level", "BLS"),
    ("payems", "PAYEMS", "비농업 고용 증감", "천 명", "M", "diff", "BLS"),
    ("ahe", "CES0500000003", "시간당 평균 임금", "%", "M", "yoy", "BLS"),
    ("civpart", "CIVPART", "경제활동참가율", "%", "M", "level", "BLS"),
    ("jolts", "JTSJOL", "구인 건수", "백만 건", "M", "scale:0.001", "BLS"),
    ("claims", "ICSA", "신규 실업수당 청구", "천 건", "W", "scale:0.001", "노동부"),
    ("gdp", "A191RL1Q225SBEA", "실질 GDP 성장률", "%", "Q", "level", "BEA"),
    ("indpro", "INDPRO", "산업생산", "%", "M", "yoy", "연준"),
    ("retail", "RSAFS", "소매판매", "%", "M", "yoy", "Census"),
    ("cfnai", "CFNAIMA3", "시카고 연은 활동지수(3개월 평균)", "지수", "M", "level", "시카고 연은"),
    ("empire", "GACDISA066MSFRBNY", "뉴욕 연은 제조업 지수", "지수", "M", "level", "뉴욕 연은"),
    ("philly", "GACDFSA066MSFRBPHI", "필라델피아 연은 제조업 지수", "지수", "M", "level", "필라델피아 연은"),
]


def _year_before(day: str) -> str:
    return f"{int(day[:4]) - 1}{day[4:]}"


def transform(rows: list, how: str) -> list:
    """[[날짜, 수준]] → 화면에 그릴 값. yoy=전년 같은 달 대비 %, diff=직전 대비 증감."""
    if how == "level":
        return [[day, round(value, 3)] for day, value in rows]
    if how.startswith("scale:"):
        factor = float(how.split(":", 1)[1])
        return [[day, round(value * factor, 3)] for day, value in rows]
    if how == "diff":
        return [[rows[i][0], round(rows[i][1] - rows[i - 1][1], 1)] for i in range(1, len(rows))]
    if how == "yoy":
        by_day = dict((day, value) for day, value in rows)
        out = []
        for day, value in rows:
            base = by_day.get(_year_before(day))
            if base:
                out.append([day, round((value / base - 1) * 100, 2)])
        return out
    raise ValueError(f"모르는 변환: {how}")


def collect(today: date, previous: dict) -> dict:
    prev = (previous.get("macro.json") or {}).get("series", {})
    series, errors = {}, []
    for key, sid, label, unit, freq, how, source in SERIES:
        start = "1999-01-01" if freq != "W" else "2015-01-01"
        try:
            rows = fred.series(sid, start)
            obs = [row for row in transform(rows, how) if row[0] >= (SINCE if freq != "W" else start)]
            if not obs:
                raise ValueError("빈 응답")
        except Exception as exc:
            if key not in prev:
                errors.append(f"{label}: {exc}")
                continue
            errors.append(f"{label}: 이번 수집 실패, 직전 수집분 유지 — {exc}")
            series[key] = prev[key]
            continue
        series[key] = {"label": label, "unit": unit, "freq": freq, "how": how,
                       "src": f"{source} (FRED {sid})", "obs": obs}
    if not series:
        raise RuntimeError("; ".join(errors) or "받은 자료 없음")
    latest = max(s["obs"][-1][0] for s in series.values())
    return {"files": {"macro.json": {"series": series}}, "latest": latest, "warnings": errors}

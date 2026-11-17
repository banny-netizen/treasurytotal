"""미국 10년물 금리와 명목 GDP 성장률, 만기별 수익률곡선.

명목 GDP(분기)·10년물 월평균·일별 10년물  FRED GDP, GS10, DGS10
만기별 수익률곡선(최근 영업일)            미 재무부 일별 수익률곡선 CSV
"""
from __future__ import annotations

from datetime import date

import common
import fred

NAME = "금리 vs 성장률"
OUTPUTS = ["growth.json"]
CURVE = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
         "daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve"
         "&field_tdr_date_value={y}&page&_format=csv")
TENORS = ["3 Mo", "6 Mo", "1 Yr", "2 Yr", "3 Yr", "5 Yr", "7 Yr", "10 Yr", "20 Yr", "30 Yr"]
FIRST_QUARTER = "1954Q1"


def quarter_of(day: str) -> str:
    return f"{day[:4]}Q{(int(day[5:7]) - 1) // 3 + 1}"


def gdp_cagr3(gdp: list) -> list:
    """분기 명목 GDP 수준 → 최근 3년(12분기) 연평균 성장률 %."""
    out = []
    for i in range(12, len(gdp)):
        now, then = gdp[i][1], gdp[i - 12][1]
        if now and then:
            out.append([quarter_of(gdp[i][0]), round(((now / then) ** (1 / 3) - 1) * 100, 2)])
    return out


def quarterly_average(monthly: list) -> list:
    """월평균 금리 → 분기 평균. 석 달이 다 있는 분기만."""
    groups: dict[str, list[float]] = {}
    for day, value in monthly:
        groups.setdefault(quarter_of(day), []).append(value)
    return [[q, round(sum(v) / len(v), 2)] for q, v in sorted(groups.items()) if len(v) == 3]


def parse_curve(text: str) -> dict | None:
    """재무부 CSV에서 가장 최근 영업일의 만기별 금리."""
    best = None
    for row in common.csv_rows(text):
        day = common.us_day(row.get("Date"))
        if not day or (best and day <= best["date"]):
            continue
        values = [common.to_float(row.get(tenor)) for tenor in TENORS]
        if sum(v is not None for v in values) >= 8:
            best = {"date": day, "tenors": TENORS, "values": values}
    return best


def collect(today: date, previous: dict) -> dict:
    warnings: list[str] = []
    prev = previous.get("growth.json") or {}
    gdp3y = [row for row in gdp_cagr3(fred.series("GDP")) if row[0] >= FIRST_QUARTER]
    y10q = [row for row in quarterly_average(fred.series("GS10")) if row[0] >= FIRST_QUARTER]
    daily = fred.series("DGS10", common.days_ago(today, 30))
    growth = dict(gdp3y)
    gaps = [rate - growth[q] for q, rate in y10q if q in growth]
    if len(gdp3y) < 200 or not gaps:
        raise ValueError("성장률·금리 자료가 부족함")

    curve = prev.get("curve")
    try:
        got = None
        for year in (today.year, today.year - 1):
            got = parse_curve(common.fetch_text(CURVE.format(y=year), timeout=60))
            if got:
                break
        if got:
            curve = got
        else:
            warnings.append("수익률곡선: 최근 자료 없음, 직전 수집분 유지")
    except common.PolicyError:
        raise
    except Exception as exc:
        warnings.append(f"수익률곡선: 이번 수집 실패, 직전 수집분 유지 — {exc}")

    data = {
        "latest_q": gdp3y[-1][0],
        "latest10y": daily[-1] if daily else prev.get("latest10y"),
        "avg_gap": round(sum(gaps) / len(gaps), 2),
        "series": {"gdp3y": gdp3y, "y10q": y10q},
        "curve": curve,
    }
    return {"files": {"growth.json": data}, "latest": data["latest_q"], "warnings": warnings}

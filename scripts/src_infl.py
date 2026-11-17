"""CPI·PCE 발표 수치. 예상치·해석·기사는 싣지 않고 공표 지수로 계산한 수치만 싣는다.

CPI  FRED(원자료 BLS). 전월비는 계절조정 지수, 전체·근원 전년비는 비계절조정 지수(공표 기준)
     품목별 가중치(상대 중요도)는 받을 수 있는 공개 API가 없어 기여도는 계산하지 않는다
PCE  DBnomics가 재배포하는 BEA 표 2.8.4(가격지수)·2.8.5(명목 지출).
     가중치 = 직전 달 명목 지출 비중, 기여도 = 가중치 × 전월비
"""
from __future__ import annotations

import re
from datetime import date

import common
import fred

NAME = "CPI·PCE 발표 수치·확산 지표"
OUTPUTS = ["infl.json", "pce.json"]
BREADTH_SINCE = "2000-01"
THRESHOLDS = (2, 3, 4)
MONTHS_KEPT = 13
DBN = "https://api.db.nomics.world/v22/series/BEA/{table}?limit=100&observations=1"

# 이름, 계절조정 시리즈, 들여쓰기 단계
CPI_ITEMS = [
    ("전체", "CPIAUCSL", 0),
    ("식품", "CPIUFDSL", 1),
    ("에너지", "CPIENGSL", 1),
    ("근원 (식품·에너지 제외)", "CPILFESL", 1),
    ("근원 재화", "CUSR0000SACL1E", 2),
    ("신차", "CUSR0000SETA01", 3),
    ("중고차", "CUSR0000SETA02", 3),
    ("의류", "CPIAPPSL", 3),
    ("근원 서비스", "CUSR0000SASLE", 2),
    ("주거", "CUSR0000SAH1", 3),
    ("의료 서비스", "CUSR0000SAM2", 3),
    ("운송 서비스", "CUSR0000SAS4", 3),
]
CPI_NSA = {"CPIAUCSL": "CPIAUCNS", "CPILFESL": "CPILFENS"}

# BEA 표 2.8.4 줄 번호 → (이름, 들여쓰기 단계, 겹치지 않는 분해 항목 여부)
PCE_LINES = {
    1: ("전체", 0, False), 25: ("근원 (식품·에너지 제외)", 1, False),
    2: ("재화", 1, False), 3: ("내구재", 2, False),
    4: ("자동차·부품", 3, True), 5: ("가구·가정용 내구재", 3, True),
    6: ("여가용 재화·차량", 3, True), 7: ("기타 내구재", 3, True),
    8: ("비내구재", 2, False),
    9: ("식료품·음료(가정 내)", 3, True), 10: ("의류·신발", 3, True),
    11: ("휘발유·기타 에너지 재화", 3, True), 12: ("기타 비내구재", 3, True),
    13: ("서비스", 1, False),
    15: ("주거·공공요금", 3, True), 16: ("의료", 3, True), 17: ("운송 서비스", 3, True),
    18: ("여가 서비스", 3, True), 19: ("음식·숙박", 3, True), 20: ("금융·보험", 3, True),
    21: ("기타 서비스", 3, True), 22: ("비영리단체 최종소비", 3, True),
}
PCE_ORDER = [1, 25, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 16, 17, 18, 19, 20, 21, 22]


def month_before(month: str, back: int = 1) -> str:
    total = int(month[:4]) * 12 + int(month[5:7]) - 1 - back
    return f"{total // 12}-{total % 12 + 1:02d}"


def pct(now: float | None, base: float | None, digits: int = 2) -> float | None:
    if now is None or not base:
        return None
    return round((now / base - 1) * 100, digits)


def changes(by_month: dict[str, float], month: str) -> dict:
    """한 지수의 전월비·직전 달 전월비·전년비."""
    now = by_month.get(month)
    prev, prev2 = by_month.get(month_before(month)), by_month.get(month_before(month, 2))
    return {"mom": pct(now, prev), "pmom": pct(prev, prev2), "yoy": pct(now, by_month.get(month_before(month, 12)))}


# ---------- CPI ----------

def cpi_releases(levels: dict[str, dict[str, float]]) -> list[dict]:
    """{시리즈: {YYYY-MM: 지수}} → 기준월별 발표 수치(최근 순)."""
    headline = levels.get("CPIAUCSL", {})
    releases = []
    for month in sorted(headline, reverse=True)[:MONTHS_KEPT]:
        items = []
        for name, sid, level in CPI_ITEMS:
            series = levels.get(sid)
            if not series or month not in series:
                continue
            row = {"n": name, "lv": level, **changes(series, month)}
            nsa = levels.get(CPI_NSA.get(sid, ""))
            if nsa:                        # 공표 전년비는 비계절조정 지수 기준
                row["yoy"] = pct(nsa.get(month), nsa.get(month_before(month, 12)))
            items.append(row)
        if items and items[0]["n"] == "전체":
            releases.append({"id": f"CPI-{month}", "kind": "CPI", "ref": month,
                             "src": "BLS (FRED 경유)", "items": items})
    return releases


# ---------- PCE ----------

def dbn_lines(data: dict) -> dict[int, dict[str, float]]:
    """DBnomics 응답 → {줄 번호: {YYYY-MM: 값}} (월간 시리즈만)."""
    out: dict[int, dict[str, float]] = {}
    for doc in data.get("series", {}).get("docs", []):
        match = re.search(r"\(line (\d+)\)", doc.get("series_name", ""))
        if not match or not str(doc.get("series_code", "")).endswith("-M"):
            continue
        values = {}
        for period, value in zip(doc.get("period", []), doc.get("value", [])):
            number = common.to_float(value)
            if number is not None and len(period) == 7:
                values[period] = number
        out[int(match.group(1))] = values
    return out


def pce_releases(price: dict[int, dict[str, float]], nominal: dict[int, dict[str, float]]) -> list[dict]:
    headline = price.get(1, {})
    releases = []
    for month in sorted(headline, reverse=True)[:MONTHS_KEPT]:
        before = month_before(month)
        total = nominal.get(1, {}).get(before)
        items = []
        for line in PCE_ORDER:
            name, level, driver = PCE_LINES[line]
            series = price.get(line)
            if not series or month not in series:
                continue
            row = {"n": name, "lv": level, **changes(series, month)}
            spend = nominal.get(line, {}).get(before)
            if total and spend is not None and line != 25:
                row["w"] = round(spend / total * 100, 2)
                if row["mom"] is not None:
                    row["c"] = round(row["w"] * pct(series[month], series.get(before), 4) / 100, 3)
            if driver:
                row["drv"] = 1
            items.append(row)
        if items and items[0]["n"] == "전체":
            releases.append({"id": f"PCE-{month}", "kind": "PCE", "ref": month,
                             "src": "BEA (DBnomics 경유)", "items": items})
    return releases


# ---------- 인플레이션 확산 지표 ----------

def breadth(price: dict[int, dict[str, float]], nominal: dict[int, dict[str, float]]) -> dict:
    """PCE 16개 품목군 가운데 물가 상승률이 기준(2·3·4%)을 넘는 품목군의 지출 비중(%).

    3개월 연율과 전년 대비 두 가지로 본다. 가중치는 직전 달 명목 지출 비중.
    """
    drivers = [line for line in PCE_ORDER if PCE_LINES[line][2]]
    months = sorted(m for m in price.get(1, {}) if m >= BREADTH_SINCE)
    obs, latest_items = [], []
    for month in months:
        before = month_before(month)
        spend = {line: nominal.get(line, {}).get(before) for line in drivers}
        if any(v is None for v in spend.values()):
            continue
        total = sum(spend.values())
        shares = {key: 0.0 for key in [f"a3_{t}" for t in THRESHOLDS] + [f"yy_{t}" for t in THRESHOLDS]}
        items, complete = [], True
        for line in drivers:
            series = price.get(line, {})
            now, m3, m12 = series.get(month), series.get(month_before(month, 3)), series.get(month_before(month, 12))
            if not now or not m3 or not m12:
                complete = False
                break
            ann3 = ((now / m3) ** 4 - 1) * 100
            yoy = (now / m12 - 1) * 100
            weight = spend[line] / total * 100
            for t in THRESHOLDS:
                if ann3 > t:
                    shares[f"a3_{t}"] += weight
                if yoy > t:
                    shares[f"yy_{t}"] += weight
            items.append({"n": PCE_LINES[line][0], "w": round(weight, 1),
                          "a3": round(ann3, 1), "yoy": round(yoy, 1)})
        if not complete:
            continue
        obs.append([month] + [round(shares[key], 1) for key in shares])
        latest_items = items
    if len(obs) < 24:
        raise ValueError("확산 지표를 계산할 자료가 부족함")
    return {"basis": "PCE 16개 품목군 (BEA 표 2.8.4·2.8.5)",
            "columns": [f"a3_{t}" for t in THRESHOLDS] + [f"yy_{t}" for t in THRESHOLDS],
            "obs": obs, "latest": obs[-1][0], "items": latest_items}


# ---------- 수집 ----------

def collect(today: date, previous: dict) -> dict:
    warnings: list[str] = []
    prev = {r["id"]: r for r in (previous.get("infl.json") or {}).get("releases", [])}
    since = f"{today.year - 3}-01-01"
    found: list[dict] = []
    files: dict = {}

    levels: dict[str, dict[str, float]] = {}
    for sid in [sid for _, sid, _ in CPI_ITEMS] + list(CPI_NSA.values()):
        try:
            levels[sid] = {day[:7]: value for day, value in fred.series(sid, since)}
        except common.PolicyError:
            raise
        except Exception as exc:
            warnings.append(f"CPI {sid}: {exc}")
    found += cpi_releases(levels)

    try:
        price = dbn_lines(common.fetch_json(DBN.format(table="NIPA-T20804"), timeout=90))
        nominal = dbn_lines(common.fetch_json(DBN.format(table="NIPA-T20805"), timeout=90))
        found += pce_releases(price, nominal)
        files["pce.json"] = breadth(price, nominal)
    except common.PolicyError:
        raise
    except Exception as exc:
        warnings.append(f"PCE: 이번 수집 실패, 직전 수집분 유지 — {exc}")

    if not found:
        raise RuntimeError("; ".join(warnings) or "받은 자료 없음")
    prev.update({r["id"]: r for r in found})
    kinds = {"CPI": [], "PCE": []}
    for release in sorted(prev.values(), key=lambda r: r["ref"], reverse=True):
        if len(kinds[release["kind"]]) < MONTHS_KEPT:
            kinds[release["kind"]].append(release)
    releases = sorted(kinds["CPI"] + kinds["PCE"], key=lambda r: (r["ref"], r["kind"]), reverse=True)
    files["infl.json"] = {"releases": releases}
    return {"files": files, "latest": releases[0]["id"], "warnings": warnings}

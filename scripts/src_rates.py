"""통화별 지표금리와 자금조달 여건.

미국  EFFR·목표범위, SOFR·SOFR 75백분위  — 뉴욕 연은 Markets API
      IORB(준비금 이자율)               — FRED
유로  €STR, 수신금리(DFR, 변경일)       — ECB Data API
일본  무담보 콜 익일물(TONA)            — 일본은행 시계열 통계 API
한국  콜금리(1일, 전체거래), KOFR       — 한국은행 ECOS (키가 없으면 sample 키로 최근 10건만)
"""
from __future__ import annotations

import os
from datetime import date

import common
import fred

NAME = "지표금리"
OUTPUTS = ["rates.json"]
SINCE = "2025-01-01"          # 보관 시작일

NYFED = "https://markets.newyorkfed.org/api/rates/{kind}/last/{count}.json"
ECB = "https://data-api.ecb.europa.eu/service/data/{key}?{query}&format=csvdata"
BOJ = ("https://www.stat-search.boj.or.jp/api/v1/getDataCode?format=json&lang=en"
       "&db=FM01&code=STRDCLUCON&startDate={start}&endDate={end}")
ECOS = "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/{count}/817Y002/D/{start}/{end}/{item}"
ECOS_ITEMS = {"call": "010101000", "kofr": "010901000"}

LABELS = {
    "effr": ("EFFR", "뉴욕 연은"),
    "effr_lo": ("연방기금 목표범위 하단", "뉴욕 연은"),
    "effr_hi": ("연방기금 목표범위 상단", "뉴욕 연은"),
    "sofr": ("SOFR", "뉴욕 연은"),
    "sofr75": ("SOFR 75백분위", "뉴욕 연은"),
    "iorb": ("준비금 이자율(IORB)", "FRED"),
    "estr": ("€STR", "ECB"),
    "dfr": ("ECB 수신금리", "ECB"),
    "tona": ("무담보 콜 익일물(TONA)", "일본은행"),
    "call": ("콜금리(1일, 전체거래)", "한국은행 ECOS"),
    "kofr": ("KOFR", "한국은행 ECOS"),
}


# ---------- 파싱 (네트워크 없이 테스트 가능) ----------

def parse_nyfed(data: dict) -> dict[str, list]:
    """refRates → 항목별 [[날짜, 값]] (오름차순)."""
    out: dict[str, list] = {"rate": [], "p75": [], "lo": [], "hi": []}
    for row in data.get("refRates", []):
        day = common.iso_day(row.get("effectiveDate"))
        if not day:
            continue
        for key, field in (("rate", "percentRate"), ("p75", "percentPercentile75"),
                           ("lo", "targetRateFrom"), ("hi", "targetRateTo")):
            value = common.to_float(row.get(field))
            if value is not None:
                out[key].append([day, value])
    return {key: sorted(rows) for key, rows in out.items()}


def parse_ecb(text: str) -> list:
    rows = []
    for row in common.csv_rows(text):
        day = common.iso_day(row.get("TIME_PERIOD"))
        value = common.to_float(row.get("OBS_VALUE"))
        if day and value is not None:
            rows.append([day, value])
    return sorted(rows)


def parse_boj(data: dict) -> list:
    if data.get("STATUS") != 200 or not data.get("RESULTSET"):
        raise ValueError(f"일본은행 API 응답 이상: {data.get('MESSAGE')}")
    values = data["RESULTSET"][0]["VALUES"]
    rows = []
    for stamp, value in zip(values["SURVEY_DATES"], values["VALUES"]):
        text = str(stamp)
        if value is None or len(text) != 8:
            continue
        rows.append([f"{text[:4]}-{text[4:6]}-{text[6:]}", float(value)])
    return sorted(rows)


def parse_ecos(data: dict) -> list:
    block = data.get("StatisticSearch")
    if not block:
        result = data.get("RESULT", {})
        if result.get("CODE") == "INFO-200":      # 해당 기간 자료 없음
            return []
        raise ValueError(f"ECOS 응답 이상: {result.get('CODE')} {result.get('MESSAGE')}")
    rows = []
    for row in block.get("row", []):
        stamp = str(row.get("TIME", ""))
        value = common.to_float(row.get("DATA_VALUE"))
        if len(stamp) == 8 and value is not None:
            rows.append([f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}", value])
    return sorted(rows)


def clean(name: str, old: list | None, new: list, warnings: list[str]) -> list:
    """범위를 벗어나거나 하루 사이 1.5%p 넘게 튄 새 값은 버리고 경고를 남긴다."""
    merged = {row[0]: row[1] for row in (old or [])}
    last = None
    for day in sorted(merged):
        last = merged[day]
    kept = []
    for day, value in sorted(new):
        if not -1.0 <= value <= 15.0:
            warnings.append(f"{name} {day} 값 {value} 범위 밖 — 제외")
            continue
        reference = merged.get(day, last)
        if reference is not None and day not in merged and abs(value - reference) > 1.5:
            warnings.append(f"{name} {day} 값 {value} 직전({reference}) 대비 급변 — 제외")
            continue
        kept.append([day, value])
        if day not in merged:
            last = value
    return common.merge_obs(old, kept, SINCE)


# ---------- 수집 ----------

def _months_back(today: date, months: int) -> str:
    total = today.year * 12 + today.month - 1 - months
    return f"{total // 12}{total % 12 + 1:02d}"


def collect(today: date, previous: dict) -> dict:
    prev = (previous.get("rates.json") or {}).get("series", {})
    first_run = not prev
    warnings: list[str] = []
    errors: list[str] = []
    fresh: dict[str, list] = {}

    def attempt(label: str, func) -> None:
        try:
            func()
        except common.PolicyError:
            raise
        except Exception as exc:
            errors.append(f"{label}: {exc}")

    count = 520 if first_run else 30

    def us_effr():
        got = parse_nyfed(common.fetch_json(NYFED.format(kind="unsecured/effr", count=count)))
        fresh["effr"], fresh["effr_lo"], fresh["effr_hi"] = got["rate"], got["lo"], got["hi"]

    def us_sofr():
        got = parse_nyfed(common.fetch_json(NYFED.format(kind="secured/sofr", count=count)))
        fresh["sofr"], fresh["sofr75"] = got["rate"], got["p75"]

    def us_iorb():
        fresh["iorb"] = fred.series("IORB", SINCE if first_run else common.days_ago(today, 60))

    def eu_estr():
        query = f"startPeriod={SINCE}" if first_run else "lastNObservations=30"
        fresh["estr"] = parse_ecb(common.fetch_text(ECB.format(key="EST/B.EU000A2X2A25.WT", query=query)))

    def eu_dfr():
        fresh["dfr"] = parse_ecb(common.fetch_text(
            ECB.format(key="FM/B.U2.EUR.4F.KR.DFR.LEV", query="lastNObservations=12")))

    def jp_tona():
        start = SINCE[:4] + SINCE[5:7] if first_run else _months_back(today, 2)
        fresh["tona"] = parse_boj(common.fetch_json(
            BOJ.format(start=start, end=f"{today.year}{today.month:02d}")))

    def kr(name: str):
        key = os.environ.get("ECOS_API_KEY", "").strip()
        if key:
            start = SINCE.replace("-", "") if (first_run or not prev.get(name, {}).get("obs")) \
                else common.days_ago(today, 45).replace("-", "")
            rows = 1000
        else:
            key, rows = "sample", 10
            start = common.days_ago(today, 13).replace("-", "")
            if not any("ECOS 키" in w for w in warnings):
                warnings.append("ECOS 키 미등록 — 한국 금리는 최근 10건만 받음")
        url = ECOS.format(key=key, count=rows, start=start, end=today.strftime("%Y%m%d"),
                          item=ECOS_ITEMS[name])
        try:
            fresh[name] = parse_ecos(common.fetch_json(url))
        except common.FetchError as exc:
            raise RuntimeError(str(exc).replace(key, "***")) from None

    attempt("EFFR", us_effr)
    attempt("SOFR", us_sofr)
    attempt("IORB", us_iorb)
    attempt("€STR", eu_estr)
    attempt("ECB 수신금리", eu_dfr)
    attempt("TONA", jp_tona)
    attempt("콜금리", lambda: kr("call"))
    attempt("KOFR", lambda: kr("kofr"))

    series = {}
    for name, (label, source) in LABELS.items():
        old = prev.get(name, {}).get("obs")
        if name in fresh:
            obs = fresh[name] if name == "dfr" else clean(label, old, fresh[name], warnings)
            if name == "dfr":
                obs = common.merge_obs(old, obs)
        else:
            obs = old or []
        if obs:
            series[name] = {"label": label, "src": source, "obs": obs}

    if not fresh:
        raise RuntimeError("; ".join(errors) or "받은 자료 없음")
    latest = max((s["obs"][-1][0] for n, s in series.items() if n != "dfr" and s["obs"]), default=None)
    return {"files": {"rates.json": {"series": series}}, "latest": latest,
            "warnings": warnings + [f"이번 수집 실패, 직전 수집분 유지 — {e}" for e in errors]}

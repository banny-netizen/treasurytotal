"""미국 재정적자(기초적자)와 국채 리프라이싱 비중.

재정수지·GDP(회계연도)  FRED FYFSD, FYGDP
순이자                  FY2014까지 FRED FYOINT, FY2015부터 재무부 월간 재정보고서(MTS) 표 9 'Net Interest'
                        (FRED FYOINT가 FY2015 이후 총이자로 바뀌어 한 시리즈로 이어 쓰면 단층이 생긴다)
리프라이싱 비중         재무부 월간 국가채무 명세(MSPD) 표 1·표 3
"""
from __future__ import annotations

import time
from datetime import date

import common
import fred

NAME = "재정적자·리프라이싱"
OUTPUTS = ["fiscal.json", "refix.json"]

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
MTS9 = (API + "/v1/accounting/mts/mts_table_9?filter=record_calendar_month:eq:09,"
        "classification_desc:eq:Net%20Interest&fields=record_fiscal_year,current_fytd_rcpt_outly_amt"
        "&page[size]=200")
MSPD1 = (API + "/v1/debt/mspd/mspd_table_1?filter=record_calendar_year:eq:{y},record_calendar_month:eq:{m:02d}"
         "&fields=record_date,security_type_desc,security_class_desc,total_mil_amt&page[size]=100")
MSPD3 = (API + "/v1/debt/mspd/mspd_table_3?filter=record_calendar_year:eq:{y},record_calendar_month:eq:{m:02d}"
         "&fields=security_class1_desc,maturity_date,outstanding_amt&page[size]=10000")

# NBER 침체 월을 포함한 회계연도 (FY1976까지 7~6월, FY1977부터 10~9월)
RECESSION_FY = [1970, 1971, 1974, 1975, 1980, 1981, 1982, 1983, 1990, 1991, 2001, 2002, 2008, 2009, 2020]
AVG_RANGE = (1962, 2019)
MTS_FROM = 2015
REFIX_START = (2001, 1)       # MSPD API가 제공하는 가장 이른 달 부근
REFIX_PER_RUN = 40            # 한 번 실행에 새로 받는 달 수 (나머지는 다음 실행에서 이어 받음)


# ---------- 재정적자 ----------

def build_fiscal(balance: list, interest_fred: list, gdp: list, mts_interest: dict[int, float],
                 min_years: int = 50) -> dict:
    """회계연도별 총적자·순이자·기초적자(GDP 대비 %). 적자가 +."""
    by_fy = lambda rows: {int(day[:4]): value for day, value in rows}
    bal, intr, out_gdp = by_fy(balance), by_fy(interest_fred), by_fy(gdp)
    primary, total, interest = [], [], []
    for fy in sorted(bal):
        if fy < AVG_RANGE[0] or fy not in out_gdp:
            continue
        net = mts_interest.get(fy) if fy >= MTS_FROM else intr.get(fy)
        if net is None:
            continue
        gdp_mil = out_gdp[fy] * 1000.0
        t = -bal[fy] / gdp_mil * 100
        i = net / gdp_mil * 100
        total.append([fy, round(t, 2)])
        interest.append([fy, round(i, 2)])
        primary.append([fy, round(t - i, 2)])
    if len(primary) < min_years:
        raise ValueError(f"회계연도 자료가 {len(primary)}개뿐")
    calm = [v for fy, v in primary if AVG_RANGE[0] <= fy <= AVG_RANGE[1] and fy not in RECESSION_FY]
    return {
        "latest": primary[-1][0],
        "avg_range": list(AVG_RANGE),
        "avg_nonrecession": round(sum(calm) / len(calm), 2),
        "recession": RECESSION_FY,
        "series": {"primary": primary, "total": total, "interest": interest},
    }


def parse_mts(data: dict) -> dict[int, float]:
    """표 9 'Net Interest' 9월(회계연도 말) 누계 → {회계연도: 백만 달러}."""
    out = {}
    for row in data.get("data", []):
        amount = common.to_float(row.get("current_fytd_rcpt_outly_amt"))
        year = row.get("record_fiscal_year")
        if amount is not None and str(year).isdigit():
            out[int(year)] = amount / 1e6
    return out


# ---------- 리프라이싱 ----------

def refix_month(table1: dict, table3: dict) -> list | None:
    """한 달치 → [기준일, 1년 안에 금리를 새로 받는 비중 %, 단기채 비중 %]. 자료가 없으면 None."""
    rows1 = table1.get("data", [])
    if not rows1:
        return None
    record = rows1[0]["record_date"]
    amount = {(r["security_type_desc"], r["security_class_desc"]): common.to_float(r["total_mil_amt"])
              for r in rows1}
    bills = amount.get(("Marketable", "Bills"))
    total = amount.get(("Total Marketable", "_"))
    frn = amount.get(("Marketable", "Floating Rate Notes")) or 0.0
    if not bills or not total:
        return None
    year, month, day = (int(p) for p in record.split("-"))
    limit = date(year + 1, month, 28 if (month == 2 and day == 29) else day).isoformat()
    soon = 0.0
    for row in table3.get("data", []):
        kind = row.get("security_class1_desc", "")
        if not (kind.startswith(("Notes", "Bonds")) or "Inflation" in kind):
            continue
        outstanding = common.to_float(row.get("outstanding_amt"))
        maturity = common.iso_day(row.get("maturity_date"))
        if outstanding is None or not maturity or maturity > limit:
            continue
        soon += outstanding
    refix = (bills + frn + soon) / total * 100
    share = bills / total * 100
    if not (5 < share < 60 and share <= refix < 80):
        raise ValueError(f"{record} 비중 계산값 이상: {refix:.1f}/{share:.1f}")
    return [record, round(refix, 2), round(share, 2)]


def _month_list(today: date) -> list[tuple[int, int]]:
    """받을 수 있는 달 목록, 최근 달부터. 직전 달 명세는 다음 달 초에 나온다."""
    months = []
    year, month = today.year, today.month
    while (year, month) > REFIX_START:
        month -= 1
        if month == 0:
            year, month = year - 1, 12
        months.append((year, month))
    return months


def collect_refix(today: date, previous: dict | None, warnings: list[str]) -> dict:
    prev = previous or {}
    have = {row[0][:7]: row for row in prev.get("obs", [])}
    empty = set(prev.get("empty", []))
    fetched = 0
    for year, month in _month_list(today):
        key = f"{year}-{month:02d}"
        if key in have or key in empty or fetched >= REFIX_PER_RUN:
            continue
        try:
            table1 = common.fetch_json(MSPD1.format(y=year, m=month))
            row = None
            if table1.get("data"):
                table3 = common.fetch_json(MSPD3.format(y=year, m=month))
                row = refix_month(table1, table3)
            fetched += 1
            time.sleep(0.3)
        except common.PolicyError:
            raise
        except Exception as exc:
            warnings.append(f"리프라이싱 {key}: {exc}")
            break
        if row:
            have[key] = row
        elif (today.year * 12 + today.month) - (year * 12 + month) > 3:
            empty.add(key)       # 오래된 달인데 자료가 없으면 다시 묻지 않는다
    obs = [have[key] for key in sorted(have)]
    remaining = sum(1 for y, m in _month_list(today)
                    if f"{y}-{m:02d}" not in have and f"{y}-{m:02d}" not in empty)
    if remaining > 1:
        warnings.append(f"리프라이싱 과거 자료 이어 받는 중 — 남은 달 {remaining}개")
    return {"obs": obs, "empty": sorted(empty)}


def collect(today: date, previous: dict) -> dict:
    warnings: list[str] = []
    files: dict = {}
    latest = None
    try:
        fiscal = build_fiscal(fred.series("FYFSD"), fred.series("FYOINT"), fred.series("FYGDP"),
                              parse_mts(common.fetch_json(MTS9)))
        files["fiscal.json"] = fiscal
        latest = f"FY{fiscal['latest']}"
    except common.PolicyError:
        raise
    except Exception as exc:
        warnings.append(f"재정적자: 이번 수집 실패, 직전 수집분 유지 — {exc}")
    refix = collect_refix(today, previous.get("refix.json"), warnings)
    if refix["obs"]:
        files["refix.json"] = refix
    if not files:
        raise RuntimeError("; ".join(warnings) or "받은 자료 없음")
    return {"files": files, "latest": latest, "warnings": warnings}

"""통화정책회의 일정·결과와 연준 점도표(SEP).

일정   연준 FOMC 일정 페이지, ECB 회의 일정 페이지, 일본은행 회의 일정 표, 한국은행 금통위 일정 표
결과   공식 금리 시계열의 변화로 판정한다 (성명서 문구를 읽지 않는다)
         연준 목표범위 상단  FRED DFEDTARU / 하단 DFEDTARL
         ECB 수신금리        ECB Data API (변경일)
         일본 콜금리(TONA)   일본은행 API — 회의 전후 콜금리 수준으로 정책금리를 추정
         한국 기준금리       한국은행 ECOS
점도표 연준 경제전망(SEP) 표의 Figure 2 분포와 Table 1의 연방기금금리 행
"""
from __future__ import annotations

import calendar
import math
import os
import re
import time
from datetime import date, timedelta

import common
import fred
import src_rates

NAME = "통화정책회의·점도표"
OUTPUTS = ["cbank.json", "dots.json"]

FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
SEP_URL = "https://www.federalreserve.gov/monetarypolicy/fomcprojtabl{stamp}.htm"
ECB_URL = "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"
BOJ_URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"
BOK_URL = "https://www.bok.or.kr/eng/main/contents.do?menuNo=400020"
ECOS_BASE = "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/{count}/722Y001/D/{start}/{end}/0101000"

MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})
MONTHS["sept"] = 9

# ECB는 지난 회의를 일정 페이지에서 지운다. 2026년 지난 회의(결정일)는 여기 적어 둔다.
ECB_PAST = ["2026-02-05", "2026-03-19", "2026-04-30", "2026-06-11", "2026-07-23", "2026-09-10", "2026-10-29"]
MAX_SEPS = 6


def plain_lines(html: str) -> list[str]:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", "\n", text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def month_number(word: str) -> int | None:
    return MONTHS.get(word.strip().lower().rstrip("."))


# ---------- 일정 파싱 ----------

def parse_fomc(html: str) -> list[dict]:
    """FOMC 일정 → [{start, date(결정일), sep}]."""
    lines = plain_lines(html)
    meetings, year, i = [], None, 0
    while i < len(lines):
        head = re.fullmatch(r"(\d{4}) FOMC Meetings", lines[i])
        if head:
            year = int(head.group(1))
        elif year and i + 1 < len(lines):
            months = [month_number(part) for part in lines[i].split("/")]
            days = re.fullmatch(r"(\d{1,2})(?:-(\d{1,2}))?(\*)?", lines[i + 1])
            if all(months) and days:
                first, last = int(days.group(1)), int(days.group(2) or days.group(1))
                start = date(year, months[0], first)
                end = date(year, months[-1], last)
                meetings.append({"start": start.isoformat(), "date": end.isoformat(),
                                 "sep": bool(days.group(3))})
                i += 1
        i += 1
    return meetings


def parse_ecb(html: str) -> list[dict]:
    """ECB 일정 → 통화정책회의 결정일(Day 2) 목록."""
    lines = plain_lines(html)
    meetings = []
    for i in range(len(lines) - 1):
        stamp = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", lines[i])
        text = lines[i + 1].lower()
        if not stamp or "monetary policy meeting" in text and "non-monetary" in text:
            continue
        if "monetary policy meeting" in text and ("day 2" in text or "press conference" in text):
            day = date(int(stamp.group(3)), int(stamp.group(2)), int(stamp.group(1)))
            meetings.append({"start": (day - timedelta(days=1)).isoformat(), "date": day.isoformat()})
    return meetings


def parse_boj(html: str) -> list[dict]:
    """일본은행 일정 표 → 금융정책결정회의 [{start, date}]."""
    meetings = []
    for caption, rows in common.html_tables(html, with_captions=True):
        year = re.search(r"(20\d{2})", caption or "")
        if not year:
            continue
        for row in rows:
            cell = row[0][0]
            match = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2})\s*\([^)]*\)(?:,\s*(?:([A-Za-z]+)\.?\s+)?(\d{1,2})\s*\([^)]*\))?", cell)
            if not match or not month_number(match.group(1)):
                continue
            month = month_number(match.group(1))
            start = date(int(year.group(1)), month, int(match.group(2)))
            end_month = month_number(match.group(3)) if match.group(3) else month
            end = date(int(year.group(1)), end_month, int(match.group(4) or match.group(2)))
            meeting = {"start": start.isoformat(), "date": end.isoformat()}
            if len(row) > 1 and row[1][0].strip() not in ("", "-", "--"):
                meeting["outlook"] = True          # 전망보고서(Outlook Report)를 내는 회의
            meetings.append(meeting)
    return meetings


def parse_bok(html: str, today: date) -> list[dict]:
    """한국은행 금통위 일정 표. 표에 연도가 없어 요일이 맞는 연도를 찾는다(올해·내년·작년)."""
    weekdays = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    meetings, used = [], set()
    for rows in common.html_tables(html)[:3]:
        cells = []
        for row in rows:
            for text, _ in row:
                match = re.fullmatch(r"([A-Za-z]+)\.\s*(\d{1,2})\s*\(([A-Za-z]{3})\)", text.strip())
                if match and month_number(match.group(1)):
                    cells.append((month_number(match.group(1)), int(match.group(2)), match.group(3).lower()))
        if len(cells) < 6:
            continue
        for year in (today.year + 1, today.year, today.year - 1):
            if year in used:
                continue
            try:
                if all(weekdays[date(year, m, d).weekday()] == w for m, d, w in cells):
                    used.add(year)
                    meetings += [{"start": date(year, m, d).isoformat(), "date": date(year, m, d).isoformat()}
                                 for m, d, _ in cells]
                    break
            except ValueError:
                continue
    return meetings


# ---------- 결과 판정 ----------

def value_on(rows: list, day: str) -> float | None:
    """day 이하에서 가장 최근 값."""
    best = None
    for stamp, value in rows:
        if stamp <= day:
            best = value
        else:
            break
    return best


def judge_step(before: float | None, after: float | None) -> dict:
    if before is None or after is None:
        return {}
    bp = round((after - before) * 100)
    return {"result": "동결" if bp == 0 else ("인상" if bp > 0 else "인하"), "chg_bp": bp}


def fed_results(meetings: list[dict], upper: list, lower: list, today: date) -> None:
    for m in meetings:
        end = date.fromisoformat(m["date"])
        if end >= today or not upper or upper[-1][0] <= m["date"]:
            continue
        after_day = (end + timedelta(days=4)).isoformat()
        m.update(judge_step(value_on(upper, m["date"]), value_on(upper, after_day)))
        hi, lo = value_on(upper, after_day), value_on(lower, after_day)
        if hi is not None and lo is not None:
            m["rate"] = f"{lo:.2f}~{hi:.2f}%"


def ecb_results(meetings: list[dict], dfr: list, today: date) -> None:
    for m in meetings:
        end = date.fromisoformat(m["date"])
        if (today - end).days < 8 or not dfr:
            continue
        before = value_on(dfr, m["date"])
        after = value_on(dfr, (end + timedelta(days=10)).isoformat())
        m.update(judge_step(before, after))
        if after is not None:
            m["rate"] = f"{after:.2f}%"
        limit = (end + timedelta(days=10)).isoformat()
        step = next((day for day, _ in dfr if m["date"] < day <= limit), None)
        if step and m.get("chg_bp"):
            m["effective"] = step                 # 바뀐 금리가 적용되는 날
        else:
            m.pop("effective", None)


def policy_from_call(rate: float) -> float:
    """콜금리(TONA) 수준에서 일본은행 정책금리를 추정한다. 콜금리는 정책금리보다 2~3bp 낮게 형성된다."""
    return round(math.ceil(rate / 0.05 - 1e-6) * 0.05, 2)


def boj_results(meetings: list[dict], tona: list, today: date) -> None:
    for m in meetings:
        start, end = date.fromisoformat(m["start"]), date.fromisoformat(m["date"])
        if (today - end).days < 6:
            continue
        before = [v for d, v in tona if (start - timedelta(days=8)).isoformat() <= d < m["start"]]
        after = [v for d, v in tona if (end + timedelta(days=2)).isoformat() <= d <= (end + timedelta(days=9)).isoformat()]
        if len(before) < 2 or len(after) < 2:
            continue
        b, a = sum(before) / len(before), sum(after) / len(after)
        bp = round((policy_from_call(a) - policy_from_call(b)) * 100) if abs(a - b) >= 0.10 else 0
        m.update({"result": "동결" if bp == 0 else ("인상" if bp > 0 else "인하"), "chg_bp": bp,
                  "rate": f"{policy_from_call(a):.2f}%", "estimated": True})


def bok_results(meetings: list[dict], today: date, warnings: list[str]) -> None:
    key = os.environ.get("ECOS_API_KEY", "").strip() or "sample"
    for m in meetings:
        end = date.fromisoformat(m["date"])
        if end >= today or m.get("result") or (today - end).days > 400:
            continue
        url = ECOS_BASE.format(key=key, count=10,
                               start=(end - timedelta(days=2)).strftime("%Y%m%d"),
                               end=(end + timedelta(days=4)).strftime("%Y%m%d"))
        try:
            rows = src_rates.parse_ecos(common.fetch_json(url))
            time.sleep(0.4)
        except common.PolicyError:
            raise
        except Exception as exc:
            warnings.append(f"한국 기준금리 {m['date']}: {str(exc).replace(key, '***')}")
            break
        before = value_on(rows, (end - timedelta(days=1)).isoformat())
        after = rows[-1][1] if rows and rows[-1][0] >= m["date"] else None
        m.update(judge_step(before, after))
        if after is not None:
            m["rate"] = f"{after:.2f}%"


# ---------- 점도표 ----------

def parse_sep(html: str) -> dict:
    """SEP 표에서 연방기금금리 전망(중앙값·중심경향·범위)과 점 분포."""
    tables = common.html_tables(html)
    summary = dots = None
    for rows in tables:
        if not rows:
            continue
        first = rows[0][0][0].lower()
        if first.startswith("midpoint of target range") and dots is None:
            dots = rows
        if summary is None and any(r and r[0][0].lower().startswith("federal funds rate") for r in rows) \
                and rows[0][0][0].lower().startswith("variable"):
            summary = rows
    if not summary or not dots:
        raise ValueError("SEP 표를 찾지 못함")

    years = [cell[0] for cell in dots[0][1:]]
    bins = []
    for row in dots[1:]:
        mid = common.to_float(row[0][0])
        if mid is None:
            continue
        counts = [int(common.to_float(cell[0]) or 0) for cell in row[1:len(years) + 1]]
        counts += [0] * (len(years) - len(counts))
        bins.append([mid, counts])
    filled = [i for i, (_, counts) in enumerate(bins) if any(counts)]
    if not filled:
        raise ValueError("점 분포가 비어 있음")
    bins = bins[filled[0]:filled[-1] + 1]
    participants = [sum(counts[i] for _, counts in bins) for i in range(len(years))]
    if not 12 <= max(participants) <= 19:
        raise ValueError(f"참가자 수 이상: {participants}")

    header = [cell[0] for cell in summary[1]]
    n = len(header) // 3
    ffr = next(r for r in summary if r[0][0].lower().startswith("federal funds rate"))
    cells = [cell[0].replace("–", "~").replace("-", "~") for cell in ffr[1:]]
    medians = [common.to_float(v) for v in cells[:n]]
    for i, year in enumerate(years):       # 표 1과 분포 표의 연도 순서가 같은지 확인
        if i < n and header[i].lower()[:4] != year.lower()[:4]:
            raise ValueError(f"연도 순서 불일치: {header[:n]} / {years}")
    return {"years": ["장기" if y.lower().startswith("longer") else y for y in years],
            "medians": medians, "ct": cells[n:2 * n], "range": cells[2 * n:3 * n],
            "bins": bins, "participants": participants}


def collect_dots(fomc: list[dict], previous: dict | None, today: date, warnings: list[str]) -> dict | None:
    have = {sep["meeting"]: sep for sep in (previous or {}).get("seps", [])}
    wanted = [m["date"] for m in fomc if m.get("sep") and m["date"] <= today.isoformat()][-MAX_SEPS:]
    for day in wanted:
        if day in have:
            continue
        try:
            sep = parse_sep(common.fetch_text(SEP_URL.format(stamp=day.replace("-", ""))))
            time.sleep(0.5)
        except common.PolicyError:
            raise
        except Exception as exc:
            warnings.append(f"점도표 {day}: {exc}")
            continue
        have[day] = {"meeting": day, "label": f"{int(day[5:7])}월 SEP", **sep}
    if not have:
        return None
    return {"seps": [have[day] for day in sorted(have)][-MAX_SEPS:]}


# ---------- 수집 ----------

def merge_meetings(old: list | None, new: list[dict], today: date) -> list[dict]:
    """직전 수집분과 합친다. 지난 회의는 지워지지 않게 남기고, 앞으로의 일정은 새로 받은 것으로 바꾼다."""
    by_day = {m["date"]: dict(m) for m in (old or []) if m["date"] < today.isoformat()}
    for m in new:
        kept = by_day.get(m["date"], {})
        by_day[m["date"]] = {**kept, **m}
    floor = f"{today.year - 1}-01-01"
    return [by_day[day] for day in sorted(by_day) if day >= floor]


def collect(today: date, previous: dict) -> dict:
    prev = {b["code"]: b for b in (previous.get("cbank.json") or {}).get("banks", [])}
    warnings: list[str] = []
    since = f"{today.year - 1}-01-01"
    banks = []

    def bank(code: str, name: str, rate_name: str, fetch_schedule, fill_results, current) -> list[dict]:
        old = prev.get(code, {})
        try:
            schedule = fetch_schedule()
        except common.PolicyError:
            raise
        except Exception as exc:
            warnings.append(f"{name} 일정: 이번 수집 실패, 직전 수집분 유지 — {exc}")
            schedule = []
        meetings = merge_meetings(old.get("meetings"), schedule, today)
        try:
            fill_results(meetings)
        except common.PolicyError:
            raise
        except Exception as exc:
            warnings.append(f"{name} 결과: {exc}")
        entry = {"code": code, "name": name, "rate_name": rate_name, "meetings": meetings}
        try:
            entry["rate"], entry["rate_asof"] = current()
        except Exception:
            entry["rate"], entry["rate_asof"] = old.get("rate"), old.get("rate_asof")
        banks.append(entry)
        return meetings

    # 연준
    fed_series: dict = {}

    def fed_fill(meetings):
        fed_series["hi"] = fred.series("DFEDTARU", since)
        fed_series["lo"] = fred.series("DFEDTARL", since)
        fed_results(meetings, fed_series["hi"], fed_series["lo"], today)

    fomc = bank("fed", "미 연준 (FOMC)", "연방기금 목표범위",
                lambda: parse_fomc(common.fetch_text(FOMC_URL)), fed_fill,
                lambda: (f"{fed_series['lo'][-1][1]:.2f}~{fed_series['hi'][-1][1]:.2f}%", fed_series["hi"][-1][0]))

    # ECB
    ecb_series: dict = {}

    def ecb_schedule():
        seeded = [{"start": (date.fromisoformat(d) - timedelta(days=1)).isoformat(), "date": d} for d in ECB_PAST]
        return seeded + parse_ecb(common.fetch_text(ECB_URL))

    def ecb_fill(meetings):
        text = common.fetch_text(src_rates.ECB.format(key="FM/B.U2.EUR.4F.KR.DFR.LEV", query="lastNObservations=16"))
        ecb_series["dfr"] = src_rates.parse_ecb(text)
        ecb_results(meetings, ecb_series["dfr"], today)

    bank("ecb", "유럽중앙은행 (ECB)", "수신금리(DFR)", ecb_schedule, ecb_fill,
         lambda: (f"{ecb_series['dfr'][-1][1]:.2f}%", ecb_series["dfr"][-1][0]))

    # 일본은행
    boj_series: dict = {}

    def boj_fill(meetings):
        url = src_rates.BOJ.format(start=f"{today.year - 1}01", end=f"{today.year}{today.month:02d}")
        boj_series["tona"] = src_rates.parse_boj(common.fetch_json(url))
        boj_results(meetings, boj_series["tona"], today)

    bank("boj", "일본은행 (BOJ)", "정책금리(콜금리로 추정)",
         lambda: parse_boj(common.fetch_text(BOJ_URL)), boj_fill,
         lambda: (f"{policy_from_call(boj_series['tona'][-1][1]):.2f}%", boj_series["tona"][-1][0]))

    # 한국은행
    bok_meetings: list = []

    def bok_fill(meetings):
        bok_meetings[:] = meetings
        bok_results(meetings, today, warnings)

    def bok_current():
        done = [m for m in bok_meetings if m.get("rate")]
        return done[-1]["rate"], done[-1]["date"]

    bank("bok", "한국은행 (금통위)", "기준금리",
         lambda: parse_bok(common.fetch_text(BOK_URL), today), bok_fill, bok_current)

    if not any(b["meetings"] for b in banks):
        raise RuntimeError("; ".join(warnings) or "받은 일정 없음")
    files: dict = {"cbank.json": {"banks": banks}}
    dots = collect_dots(fomc, previous.get("dots.json"), today, warnings)
    if dots:
        files["dots.json"] = dots
    upcoming = sorted(m["date"] for b in banks for m in b["meetings"] if m["date"] >= today.isoformat())
    return {"files": files, "latest": upcoming[0] if upcoming else None, "warnings": warnings}

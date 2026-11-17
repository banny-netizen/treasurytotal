"""연준 모델: S&P 500 선행 이익수익률(100 ÷ 선행 PER) vs 미 국채 10년물.

선행 12개월 PER  FactSet Earnings Insight 주간 보고서(공개 PDF)의 문장에서 숫자만 읽는다
10년물           FRED DGS10 — 보고서 발행 전 영업일 값과 짝짓는다

보고서 본문은 저장하지 않는다. 상대 서버가 호출을 막으면(403·429) 그 자리에서 멈추고 다음 실행을 기다린다.
"""
from __future__ import annotations

import re
import time
from collections import Counter
from datetime import date, timedelta

import common
import fred
import pdftext

NAME = "연준 모델"
OUTPUTS = ["fedmodel.json"]
BASE = ("https://insight.factset.com/hubfs/Website/Resources%20Section/Research%20Desk/"
        "Earnings%20Insight/EarningsInsight_{tag}.pdf")
PAUSE = 1.6              # 호출 사이 간격(초)
MAX_REQUESTS = 90        # 한 번 실행에 보내는 호출 수 상한
BACKFILL_WEEKS = 56      # 처음 실행할 때 거슬러 올라가는 주 수

_DASH = "[-‐‑‒–]"
PER_RE = re.compile(r"forward12" + _DASH + r"?monthP/Eratio(?:fortheS&P500)?is(\d{1,2}\.\d)", re.I)
AVG5_RE = re.compile(r"5" + _DASH + r"?yearaverage\((\d{1,2}\.\d)\)", re.I)
AVG10_RE = re.compile(r"10" + _DASH + r"?yearaverage\((\d{1,2}\.\d)\)", re.I)


def read_report(text: str) -> dict | None:
    """보고서 글자에서 선행 PER(가장 많이 나온 값)과 5년·10년 평균. PER 문장이 없으면 None."""
    flat = re.sub(r"\s+", "", text)
    found = PER_RE.findall(flat)
    if not found:
        return None
    per = float(Counter(found).most_common(1)[0][0])
    if not 8 <= per <= 40:
        return None
    a5, a10 = AVG5_RE.search(flat), AVG10_RE.search(flat)
    return {"per": per, "mentions": len(found),
            "a5": float(a5.group(1)) if a5 else None,
            "a10": float(a10.group(1)) if a10 else None}


def tag_of(day: date) -> str:
    return day.strftime("%m%d%y")


def day_of(tag: str) -> date:
    return date(2000 + int(tag[4:6]), int(tag[:2]), int(tag[2:4]))


def candidates(last: date | None, today: date) -> list[date]:
    """확인할 금요일 목록(오래된 것부터)."""
    start = last + timedelta(days=1) if last else today - timedelta(weeks=BACKFILL_WEEKS)
    day = start + timedelta(days=(4 - start.weekday()) % 7)
    out = []
    while day <= today:
        out.append(day)
        day += timedelta(days=7)
    return out


def pair_yield(asof: date, yields: dict[str, float]) -> tuple[str, float] | None:
    """asof 이하에서 가장 가까운 영업일의 10년물."""
    for back in range(0, 7):
        key = (asof - timedelta(days=back)).isoformat()
        if key in yields:
            return key, yields[key]
    return None


def collect(today: date, previous: dict) -> dict:
    prev = previous.get("fedmodel.json") or {}
    obs = {row[3]: row for row in prev.get("obs", [])}      # 태그 → [기준일, PER, 10년물, 태그]
    avg = dict(prev.get("avg") or {})
    warnings: list[str] = []
    last = max((day_of(tag) for tag in obs), default=None)
    todo = candidates(last, today)
    first = (todo[0] if todo else today) - timedelta(days=10)
    yields = dict(fred.series("DGS10", first.isoformat()))

    requests = 0
    blocked = False
    for friday in todo:
        if blocked or requests >= MAX_REQUESTS:
            break
        for issue in (friday, friday - timedelta(days=1)):       # 금요일이 휴일이면 목요일에 나온다
            if requests >= MAX_REQUESTS:
                break
            tag = tag_of(issue)
            try:
                requests += 1
                body = common.fetch(BASE.format(tag=tag), retries=1, timeout=60)
            except common.FetchError as exc:
                time.sleep(PAUSE)
                if exc.status == 404:
                    continue
                warnings.append(f"FactSet 호출 중단({tag}): {exc}")
                blocked = True
                break
            time.sleep(PAUSE)
            if body[:5] != b"%PDF-":
                warnings.append(f"FactSet {tag}: PDF가 아닌 응답 — 호출 중단")
                blocked = True
                break
            report = read_report(pdftext.extract(body))
            if not report:
                warnings.append(f"FactSet {tag}: 선행 PER 문장 없음(특별호) — 건너뜀")
                break
            paired = pair_yield(issue - timedelta(days=1), yields)
            if not paired:
                warnings.append(f"FactSet {tag}: 짝지을 10년물 없음 — 다음 실행에서 다시 시도")
                break
            previous_per = obs[max(obs, key=day_of)][1] if obs else None
            if previous_per is not None and abs(report["per"] - previous_per) > 2.5 and last and \
                    (issue - last).days <= 14:
                warnings.append(f"FactSet {tag}: PER {report['per']} 직전({previous_per}) 대비 급변 — 제외")
                break
            obs[tag] = [paired[0], report["per"], paired[1], tag]
            last = issue
            if report["a5"] and report["a10"]:
                avg = {"a5": report["a5"], "a10": report["a10"]}
            break
    if not obs:
        raise RuntimeError("; ".join(warnings) or "받은 보고서 없음")
    rows = sorted(obs.values(), key=lambda row: row[0])
    data = {"avg": avg, "obs": rows}
    return {"files": {"fedmodel.json": data}, "latest": rows[-1][0], "warnings": warnings}

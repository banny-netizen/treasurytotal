"""수집 진입점. 출처별로 따로 받아 docs/data/ 에 쓴다.

사용: python3 scripts/collect.py [묶음 또는 출처 이름 ...]
      묶음: daily(기본), weekly, all

- 한 출처가 실패해도 나머지는 진행하고, 실패한 출처는 직전 수집분을 그대로 둔다.
- 내용이 바뀐 파일만 다시 쓴다.
- 출처별 결과(성공 여부, 최근 자료 시점, 경고, 오류)는 docs/data/_status.json 에 남긴다.
- 허용 목록 밖 주소를 부르려 한 경우(PolicyError)에만 전체를 멈춘다.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import common
import src_cbank
import src_delinq
import src_fedmodel
import src_fiscal
import src_growth
import src_infl
import src_macro
import src_rates

SOURCES = {
    "rates": src_rates,
    "cbank": src_cbank,
    "macro": src_macro,
    "infl": src_infl,
    "delinq": src_delinq,
    "fiscal": src_fiscal,
    "growth": src_growth,
    "fedmodel": src_fedmodel,
}
GROUPS = {
    "daily": ["rates", "cbank", "macro", "infl", "delinq", "fiscal", "growth"],
    "weekly": ["fedmodel"],
    "all": list(SOURCES),
}
STATUS_PATH = common.DATA_DIR / "_status.json"


def resolve(args: list[str]) -> list[str]:
    names: list[str] = []
    for arg in args or ["daily"]:
        for name in GROUPS.get(arg, [arg]):
            if name not in SOURCES:
                raise SystemExit(f"모르는 출처: {name}")
            if name not in names:
                names.append(name)
    return names


def run_one(name: str, now: datetime, status: dict) -> bool:
    module = SOURCES[name]
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    previous = {fname: common.read_json(common.DATA_DIR / fname) for fname in module.OUTPUTS}
    entry = dict(status.get(name) or {})
    entry.update({"name": module.NAME, "files": module.OUTPUTS, "checked_at": stamp})
    try:
        result = module.collect(now.date(), previous)
        changed = []
        for fname, data in result["files"].items():
            if fname not in module.OUTPUTS:
                raise RuntimeError(f"등록되지 않은 산출 파일: {fname}")
            if data is not None and data != previous.get(fname):
                common.write_json(common.DATA_DIR / fname, data)
                changed.append(fname)
        entry.update({"ok": True, "error": None, "latest": result.get("latest"),
                      "warnings": [str(w)[:300] for w in result.get("warnings", [])][:12]})
        if changed or "updated_at" not in entry:
            entry["updated_at"] = stamp
        print(f"완료  {module.NAME}: 최근 {result.get('latest')}, 바뀐 파일 {changed or '없음'}")
        for warning in entry["warnings"]:
            print(f"      경고: {warning}")
        ok = True
    except common.PolicyError:
        raise
    except Exception as exc:
        entry.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:400]})
        print(f"실패  {module.NAME}: {entry['error']}")
        ok = False
    status[name] = entry
    return ok


def main() -> int:
    names = resolve(sys.argv[1:])
    now = datetime.now(timezone.utc)
    saved = common.read_json(STATUS_PATH) or {}
    status = saved.get("sources", {})
    succeeded = sum(run_one(name, now, status) for name in names)
    common.write_json(STATUS_PATH, {
        "checked_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": {name: status[name] for name in SOURCES if name in status},
    })
    print(f"{succeeded}/{len(names)}개 출처 수집")
    return 0 if succeeded else 1


if __name__ == "__main__":
    sys.exit(main())

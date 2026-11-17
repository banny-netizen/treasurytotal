"""운영 정책 점검. 어긋나는 것이 있으면 실패(종료 코드 1)한다.

1. 스크립트와 화면에 적힌 주소는 모두 허용 목록에 있어야 한다.
2. docs/data/ 에는 등록된 산출 파일만 있어야 한다.
3. 엑셀·PDF 같은 수동 자료는 저장소에 둘 수 없다.
4. API 키처럼 보이는 값이 파일에 적혀 있으면 안 된다(키는 저장소 Secrets에만 둔다).
"""
from __future__ import annotations

import re
import sys
from urllib.parse import urlsplit

from common import ROOT, load_allowlist

URL_RE = re.compile(r"https?://[^\s\"'<>)\]}`]+")
KEY_RE = re.compile(r"(?i)(api[_-]?key|userid|registrationkey)\s*[=:]\s*[\"']?[A-Za-z0-9-]{20,}")
SCAN_DIRS = ("scripts", "docs", ".github")
SCAN_SUFFIXES = {".py", ".html", ".js", ".css", ".yml", ".json"}
BANNED_SUFFIXES = {
    ".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".pdf", ".doc", ".docx",
    ".ppt", ".pptx", ".hwp", ".hwpx", ".zip", ".7z", ".msg", ".eml",
}
SKIP_PARTS = {".git", "__pycache__", "node_modules"}
# 수집 대상이 아니라 화면·설명에서 가리키기만 하는 주소
REFERENCE_PREFIXES = ("https://github.com/banny-netizen/",)


def tracked_files():
    for path in ROOT.rglob("*"):
        if path.is_file() and not SKIP_PARTS.intersection(path.parts):
            yield path


def main() -> int:
    allow = load_allowlist()
    hosts = set(allow["hosts"])
    outputs = set(allow["outputs"])
    identifiers = set(allow.get("identifiers", []))
    problems: list[str] = []

    for path in tracked_files():
        rel = path.relative_to(ROOT).as_posix()

        if path.suffix.lower() in BANNED_SUFFIXES:
            problems.append(f"{rel}: 수동 자료 형식은 올릴 수 없음")

        if rel.startswith("docs/data/") and path.name not in outputs:
            problems.append(f"{rel}: 등록되지 않은 데이터 파일 (config/allowlist.json outputs)")

        if rel.split("/")[0] in SCAN_DIRS and path.suffix.lower() in SCAN_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
            if KEY_RE.search(text):
                problems.append(f"{rel}: API 키로 보이는 값이 적혀 있음")
            for url in sorted(set(URL_RE.findall(text))):
                if url in identifiers or url.startswith(REFERENCE_PREFIXES):
                    continue
                parts = urlsplit(url)
                if parts.scheme != "https" or parts.hostname not in hosts:
                    problems.append(f"{rel}: 허용 목록에 없는 주소 {url[:120]}")

    if problems:
        print("정책 점검 실패")
        for line in problems:
            print(" -", line)
        return 1
    print(f"정책 점검 통과 (허용 주소 {len(hosts)}곳, 산출 파일 {len(outputs)}개)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

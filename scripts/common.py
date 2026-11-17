"""공용 함수. 허용 목록(config/allowlist.json)에 등록된 주소만 호출한다."""
from __future__ import annotations

import csv
import io
import json
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_PATH = ROOT / "config" / "allowlist.json"
DATA_DIR = ROOT / "docs" / "data"
USER_AGENT = "treasurytotal/1.0 (public-data collector; +https://github.com/banny-netizen/treasurytotal)"


class PolicyError(RuntimeError):
    """운영 정책에 어긋나는 호출. 수집 전체를 멈춘다."""


class RedirectRefused(RuntimeError):
    """상대 서버가 허용 목록 밖으로 넘기려 해서 따라가지 않았다. 해당 출처만 실패로 처리한다."""


class FetchError(RuntimeError):
    """받아 오지 못함. status 는 HTTP 상태 코드(없으면 None)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


_allowlist_cache: dict | None = None


def load_allowlist() -> dict:
    global _allowlist_cache
    if _allowlist_cache is None:
        _allowlist_cache = json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))
    return _allowlist_cache


def check_url(url: str) -> None:
    """https이고 허용 목록에 있는 호스트인지 확인한다. 아니면 PolicyError."""
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise PolicyError(f"https가 아닌 주소: {url}")
    if parts.hostname not in load_allowlist()["hosts"]:
        raise PolicyError(f"허용 목록에 없는 주소: {parts.hostname}")


class _CheckedRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가기 전에 목적지도 허용 목록으로 검사한다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            check_url(newurl)
        except PolicyError:
            host = urlsplit(newurl).hostname or "알 수 없는 주소"
            raise RedirectRefused(f"허용 목록 밖 주소({host})로 넘기려 해서 따라가지 않음") from None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_CheckedRedirect)


def fetch(url: str, timeout: int = 40, retries: int = 3, pause: float = 2.0,
          data: bytes | None = None, headers: dict | None = None) -> bytes:
    """허용된 주소에서 본문을 받아 온다. 일시 오류는 몇 번 다시 시도한다.

    403·404·429 처럼 다시 불러도 바뀌지 않는 응답은 바로 실패로 처리한다
    (차단·봇 확인을 반복 호출로 넘어가려 하지 않는다).
    """
    check_url(url)
    last: Exception | None = None
    status: int | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"User-Agent": USER_AGENT, "Accept": "*/*", **(headers or {})},
            )
            with _opener.open(req, timeout=timeout) as resp:
                return resp.read()
        except (PolicyError, RedirectRefused):
            raise
        except urllib.error.HTTPError as exc:
            last, status = exc, exc.code
            if exc.code in (400, 401, 403, 404, 410, 429):
                break
        except Exception as exc:  # 네트워크 오류
            last, status = exc, None
        if attempt < retries - 1:
            time.sleep(pause * (attempt + 1))
    host = urlsplit(url).hostname
    raise FetchError(f"수집 실패: {host} ({'HTTP ' + str(status) if status else last})", status)


def decode_text(body: bytes) -> str:
    for encoding in ("utf-8-sig", "cp949", "cp932"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def fetch_text(url: str, **kwargs) -> str:
    return decode_text(fetch(url, **kwargs))


def fetch_json(url: str, **kwargs):
    return json.loads(fetch(url, **kwargs))


# ---------- 값 다루기 ----------

def to_float(value) -> float | None:
    """숫자 문자열을 float로. 빈 값, "null", "-", "." 은 None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").rstrip("%").strip()
    if text in ("", "-", ".", "N/A", "NA", "ND") or text.lower() in ("null", "nan"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def iso_day(value) -> str | None:
    """'2026-11-12T00:00:00' 같은 값에서 날짜만. 형식이 다르면 None."""
    text = str(value or "").strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-" and text[:4].isdigit():
        return text[:10]
    return None


def us_day(value) -> str | None:
    """'11/12/2026' → '2026-11-12'."""
    parts = str(value or "").strip().split("/")
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        month, day, year = (int(p) for p in parts)
        if year < 100:
            year += 2000
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def days_ago(today: date, days: int) -> str:
    return (today - timedelta(days=days)).isoformat()


def csv_rows(text: str) -> list[dict]:
    """머리글이 있는 CSV → 행(dict) 목록."""
    return list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))


def merge_obs(old: list | None, new: list, since: str | None = None) -> list:
    """[[날짜, 값...], ...] 두 목록을 합친다. 같은 날짜는 새 값이 이긴다. 날짜 오름차순."""
    by_day = {row[0]: row for row in (old or []) if row}
    by_day.update({row[0]: row for row in new if row})
    return [by_day[day] for day in sorted(by_day) if since is None or day >= since]


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


# ---------- HTML ----------

class _TableParser(HTMLParser):
    """HTML 표를 [표][행][(글자, 첫 링크)] 로 뽑는다. 표 제목(caption)도 함께 둔다."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, str | None]]]] = []
        self.captions: list[str] = []
        self._open: list[dict] = []
        self._row: list | None = None
        self._cell: dict | None = None
        self._caption: list | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._open.append({"rows": [], "caption": ""})
        elif tag == "caption" and self._open:
            self._caption = []
        elif tag == "tr" and self._open:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"text": [], "href": None}
        elif tag == "a" and self._cell is not None:
            href = dict(attrs).get("href")
            if href and not self._cell["href"]:
                self._cell["href"] = href.strip()
        elif tag == "br" and self._cell is not None:
            self._cell["text"].append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell["text"]).split())
            self._row.append((text, self._cell["href"]))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._open and self._row:
                self._open[-1]["rows"].append(self._row)
            self._row = None
        elif tag == "caption" and self._caption is not None and self._open:
            self._open[-1]["caption"] = " ".join("".join(self._caption).split())
            self._caption = None
        elif tag == "table" and self._open:
            table = self._open.pop()
            self.tables.append(table["rows"])
            self.captions.append(table["caption"])

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"].append(data)
        elif self._caption is not None:
            self._caption.append(data)


def html_tables(html: str, with_captions: bool = False):
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    if with_captions:
        return list(zip(parser.captions, parser.tables))
    return parser.tables


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.links.append((" ".join("".join(self._text).split()), self._href.strip()))
            self._href = None

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)


def html_links(html: str) -> list[tuple[str, str]]:
    """문서 안의 링크를 (글자, 주소) 목록으로."""
    parser = _LinkParser()
    parser.feed(html)
    parser.close()
    return parser.links

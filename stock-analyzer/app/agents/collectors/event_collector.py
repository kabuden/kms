"""이벤트 수집기 — 실적 발표(Yahoo Finance·DART) + 내부자 거래(SEC EDGAR Form 4).

표준 라이브러리(urllib, xml.etree.ElementTree, json)만 사용.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from ...events import EarningsEvent, InsiderTrade, categorize_surprise

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _get(url: str, timeout: int = 12) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA,
            "Accept-Encoding": "identity",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


# ───────────────────────────────────────────────
# 미국 실적 — Yahoo Finance earningsHistory
# ───────────────────────────────────────────────
_YF_EARNINGS_URL = (
    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
    "?modules=earningsHistory&crumb=null"
)


def fetch_us_earnings(symbol: str, limit: int = 8) -> list[EarningsEvent]:
    """Yahoo Finance earningsHistory에서 최근 실적 이력(미국 종목)."""
    raw = _get(_YF_EARNINGS_URL.format(sym=symbol))
    if not raw:
        return []
    try:
        data = json.loads(raw.decode())
        history = (data["quoteSummary"]["result"][0]
                   ["earningsHistory"]["history"])
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return []

    events: list[EarningsEvent] = []
    for item in history[-limit:]:
        try:
            ts = (item.get("quarter") or {}).get("raw")
            if ts is None:
                continue
            event_date = datetime.utcfromtimestamp(ts).date().isoformat()
            actual = (item.get("epsActual") or {}).get("raw")
            expected = (item.get("epsEstimate") or {}).get("raw")
            surprise = (item.get("surprisePercent") or {}).get("raw")
            if surprise is None and actual is not None and expected:
                try:
                    surprise = (actual - expected) / abs(expected) * 100.0
                except ZeroDivisionError:
                    surprise = None
            events.append(EarningsEvent(
                symbol=symbol,
                event_date=event_date,
                event_type=categorize_surprise(surprise),
                surprise_pct=round(surprise, 2) if surprise is not None else 0.0,
                actual_eps=actual,
                expected_eps=expected,
                source="yfinance",
            ))
        except Exception:
            continue
    return events


# ───────────────────────────────────────────────
# 한국 실적 — DART OpenAPI (API 키 필요)
# ───────────────────────────────────────────────
def fetch_kr_earnings(symbol: str) -> list[EarningsEvent]:
    """DART OpenAPI 연결(SA_DART_API_KEY 없으면 빈 리스트).

    TODO: DART corp_code 매핑 + fnlttSinglAcnt 완성.
          현재는 키 존재 확인만 하고 실제 파싱은 미구현.
    """
    if not os.environ.get("SA_DART_API_KEY", ""):
        return []
    # 미구현 — 향후 DART corp_code 조회 + 보고서 파싱 추가
    return []


# ───────────────────────────────────────────────
# SEC EDGAR — ticker→CIK 매핑
# ───────────────────────────────────────────────
_EDGAR_CIK_JSON = "https://www.sec.gov/files/company_tickers.json"
_CIK_CACHE: dict[str, int] = {}


def _cik_for(symbol: str) -> int | None:
    """ticker 심볼로 SEC CIK 번호 조회 (캐시 공유)."""
    if not _CIK_CACHE:
        raw = _get(_EDGAR_CIK_JSON, timeout=15)
        if raw:
            try:
                data = json.loads(raw.decode())
                for _, info in data.items():
                    t = (info.get("ticker") or "").upper()
                    c = info.get("cik_str")
                    if t and c:
                        _CIK_CACHE[t] = int(c)
            except Exception:
                pass
    return _CIK_CACHE.get(symbol.upper())


# ───────────────────────────────────────────────
# SEC EDGAR — Form 4 RSS 파싱
# ───────────────────────────────────────────────
_EDGAR_FORM4_RSS = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcompany&CIK={cik}&type=4&dateb=&owner=include"
    "&count=40&output=atom"
)

_ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}


def _parse_rss_trades(xml_bytes: bytes, symbol: str) -> list[InsiderTrade]:
    """EDGAR Form 4 RSS XML → InsiderTrade 리스트(단순 버전)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []

    trades: list[InsiderTrade] = []
    for entry in root.findall("a:entry", _ATOM_NS):
        try:
            title_el = entry.find("a:title", _ATOM_NS)
            title = (title_el.text or "") if title_el is not None else ""
            updated_el = entry.find("a:updated", _ATOM_NS)
            filed_date = ""
            if updated_el is not None and updated_el.text:
                filed_date = updated_el.text[:10]
            if not filed_date:
                continue

            summary_el = entry.find("a:summary", _ATOM_NS)
            summary_raw = (summary_el.text or "") if summary_el is not None else ""
            summary = summary_raw.lower()

            # 10b5-1 계획 여부
            is_scheduled = "10b5-1" in summary

            # 거래 유형 추론 (RSS summary 텍스트에서 키워드)
            if any(kw in summary for kw in ("purchase", "acquisition", "買")):
                txn_type = "P"
            elif any(kw in summary for kw in ("sale", "disposition", "disposal")):
                txn_type = "S"
            else:
                txn_type = "A"

            # 신고자 이름: title 형식 "4 - FILER NAME (CIK) (COMPANY)"
            filer = "Unknown"
            m = re.match(r"4\s*-\s*(.+?)\s*\(", title)
            if m:
                filer = m.group(1).strip()

            # 주식수·가격 추출 시도 (RSS summary 에 가끔 포함됨)
            shares = _extract_num(summary, r"(\d[\d,\.]+)\s*shares?")
            price = _extract_num(summary, r"\$\s*([\d,\.]+)\s*per\s*share")
            total = shares * price if shares and price else 0.0

            trades.append(InsiderTrade(
                symbol=symbol,
                filed_date=filed_date,
                transaction_date=filed_date,  # 정확한 거래일은 XBRL 파싱 필요
                filer=filer,
                role="Unknown",
                transaction_type=txn_type,
                shares=shares or 0.0,
                price_per_share=price or 0.0,
                total_value=total,
                form_type="4",
                is_scheduled=is_scheduled,
            ))
        except Exception:
            continue
    return trades


def _extract_num(text: str, pattern: str) -> float:
    m = re.search(pattern, text)
    if not m:
        return 0.0
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return 0.0


def fetch_insider_trades(symbol: str, days_back: int = 45) -> list[InsiderTrade]:
    """SEC EDGAR Form 4 RSS에서 최근 내부자 거래(미국 종목 전용)."""
    cik = _cik_for(symbol)
    if not cik:
        return []
    raw = _get(_EDGAR_FORM4_RSS.format(cik=cik), timeout=15)
    if not raw:
        return []
    trades = _parse_rss_trades(raw, symbol)
    cutoff = (datetime.utcnow().date() - timedelta(days=days_back)).isoformat()
    return [t for t in trades if t.filed_date >= cutoff]


# ───────────────────────────────────────────────
# 통합 진입점
# ───────────────────────────────────────────────
def collect_events(symbol: str, market: str) -> dict:
    """심볼별 이벤트(실적+내부자거래) 수집.

    반환: {"earnings": list[EarningsEvent], "insiders": list[InsiderTrade]}
    """
    earnings: list[EarningsEvent] = []
    insiders: list[InsiderTrade] = []

    if market == "US":
        if not symbol.startswith("^"):
            earnings = fetch_us_earnings(symbol)
            insiders = fetch_insider_trades(symbol, days_back=45)
    elif market == "KR":
        if not symbol.startswith("^"):
            earnings = fetch_kr_earnings(symbol)

    return {"earnings": earnings, "insiders": insiders}

"""펀더멘털 수집기 — Yahoo Finance quoteSummary로 밸류·퀄리티 지표 수집.

표준 라이브러리(urllib, json)만 사용.
밸류 팩터(PER·PBR·PSR)와 퀄리티 팩터(ROE·부채비율·이익률)에 쓰는
재무 스냅샷을 종목별로 1건씩 받아온다(느리게 변하므로 갱신 빈도 낮아도 됨).

⚠️ Yahoo quoteSummary 엔드포인트는 시점에 따라 crumb/cookie 를 요구할 수 있다.
실패하면 빈 결과를 반환하고, 예측기들은 중립(0)으로 폴백한다.
"""
from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime


_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_QS_URL = (
    "https://query2.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
    "?modules=defaultKeyStatistics,financialData,summaryDetail&crumb=null"
)


@dataclass
class Fundamentals:
    symbol: str
    as_of: str
    pe: float | None = None              # 후행 PER
    forward_pe: float | None = None      # 선행 PER
    pb: float | None = None              # PBR (주가/순자산)
    ps: float | None = None              # PSR (주가/매출)
    roe: float | None = None             # 자기자본이익률 (소수, 0.35=35%)
    debt_to_equity: float | None = None  # 부채비율 (야후는 %단위, 150=1.5배)
    profit_margin: float | None = None   # 순이익률 (소수)
    current_ratio: float | None = None   # 유동비율
    beta: float | None = None            # 시장 민감도
    dividend_yield: float | None = None  # 배당수익률 (소수)
    source: str = "yfinance"


def _get(url: str, timeout: int = 12) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": _UA, "Accept-Encoding": "identity"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _raw(node: dict, *keys: str) -> float | None:
    """quoteSummary 의 {…: {'raw': 값}} 구조에서 raw 값을 안전하게 꺼낸다."""
    for k in keys:
        v = node.get(k)
        if isinstance(v, dict) and "raw" in v:
            try:
                return float(v["raw"])
            except (TypeError, ValueError):
                return None
    return None


def fetch_fundamentals(symbol: str) -> Fundamentals | None:
    """Yahoo Finance에서 종목 재무 스냅샷. 실패 시 None."""
    raw = _get(_QS_URL.format(sym=symbol))
    if not raw:
        return None
    try:
        result = json.loads(raw.decode())["quoteSummary"]["result"][0]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None

    stats = result.get("defaultKeyStatistics", {}) or {}
    fin = result.get("financialData", {}) or {}
    summ = result.get("summaryDetail", {}) or {}

    f = Fundamentals(
        symbol=symbol,
        as_of=datetime.utcnow().date().isoformat(),
        pe=_raw(summ, "trailingPE"),
        forward_pe=_raw(stats, "forwardPE") or _raw(summ, "forwardPE"),
        pb=_raw(stats, "priceToBook"),
        ps=_raw(summ, "priceToSalesTrailing12Months"),
        roe=_raw(fin, "returnOnEquity"),
        debt_to_equity=_raw(fin, "debtToEquity"),
        profit_margin=_raw(fin, "profitMargins"),
        current_ratio=_raw(fin, "currentRatio"),
        beta=_raw(stats, "beta") or _raw(summ, "beta"),
        dividend_yield=_raw(summ, "dividendYield"),
    )
    # 모든 지표가 비었으면 의미 없는 응답으로 보고 None
    if all(getattr(f, k) is None for k in (
            "pe", "pb", "ps", "roe", "debt_to_equity", "profit_margin")):
        return None
    return f

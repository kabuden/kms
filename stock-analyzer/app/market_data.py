"""시세 데이터 제공자 (무료·API키 불필요).

우선순위:
  1) 온라인(SA_OFFLINE=false): Yahoo Finance 차트 JSON 엔드포인트를 표준
     라이브러리(urllib)로 호출 → pandas/yfinance 없이 일봉 종가 수집.
     같은 프로세스 안에서는 심볼별 전체 시계열을 1회만 받아 캐시한다
     (백테스트/시드 시 호출 폭증·레이트리밋 방지).
  2) 실패 시: 결정론적 합성 시계열로 폴백(오프라인 데모와 동일, 재현 가능).
"""
from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from datetime import datetime, timedelta

from .config import SETTINGS

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_CHART_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/"
              "{sym}?range=1y&interval=1d")

# 프로세스 수명 동안 심볼별 (date, close) 시계열 캐시
_SERIES_CACHE: dict[str, list[tuple[str, float]]] = {}


# ───────────────────────── 합성(폴백) ─────────────────────────
def _seed(symbol: str, day: str) -> int:
    h = hashlib.sha256(f"{symbol}:{day}".encode()).hexdigest()
    return int(h[:8], 16)


def _synthetic_series(symbol: str, end_day: str, length: int) -> list[float]:
    base_seed = _seed(symbol, "base")
    price = 50.0 + (base_seed % 200)
    series: list[float] = []
    d = datetime.fromisoformat(end_day).date() - timedelta(days=length)
    for i in range(length):
        day = (d + timedelta(days=i)).isoformat()
        s = _seed(symbol, day)
        daily = ((s % 3000) / 1000.0 - 1.5) / 100.0
        trend = math.sin((base_seed % 100 + i) / 9.0) * 0.004
        price *= (1.0 + daily + trend)
        series.append(round(price, 2))
    return series


def _synthetic_realized(symbol: str, cycle_date: str) -> float:
    next_day = (datetime.fromisoformat(cycle_date).date() + timedelta(days=1)).isoformat()
    s = _seed(symbol, next_day)
    base = _seed(symbol, "base")
    daily = ((s % 3000) / 1000.0 - 1.5)
    trend = math.sin((base % 100) / 9.0) * 0.4
    return round(daily + trend, 3)


# ───────────────────────── Yahoo 실데이터 ─────────────────────────
def _fetch_yahoo_series(symbol: str) -> list[tuple[str, float]]:
    """심볼의 최근 1년 일봉 (date, close) 오름차순. 실패 시 빈 리스트."""
    if symbol in _SERIES_CACHE:
        return _SERIES_CACHE[symbol]
    series: list[tuple[str, float]] = []
    try:
        req = urllib.request.Request(_CHART_URL.format(sym=symbol),
                                     headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        result = data["chart"]["result"][0]
        ts = result["timestamp"]
        closes = result["indicators"]["quote"][0]["close"]
        for t, c in zip(ts, closes):
            if c is None:
                continue
            day = datetime.utcfromtimestamp(t).date().isoformat()
            series.append((day, float(c)))
    except Exception:
        series = []
    _SERIES_CACHE[symbol] = series
    return series


def price_history(symbol: str, end_day: str, length: int = 30) -> list[float]:
    """end_day(포함) 이전 length 거래일의 종가. 실패 시 합성 폴백."""
    if not SETTINGS.offline:
        series = _fetch_yahoo_series(symbol)
        closes = [c for d, c in series if d <= end_day]
        if len(closes) >= 2:
            return closes[-length:]
    return _synthetic_series(symbol, end_day, length)


def realized_return_pct(symbol: str, cycle_date: str) -> float | None:
    """cycle_date 에 내린 예측의 실현 수익률(%) = 다음 거래일 종가 변화율.

    실데이터에서 다음 거래일 종가가 아직 없으면(미래) None 을 반환하고,
    평가는 그 종목을 건너뛴다(다음에 데이터가 생기면 평가 가능).
    """
    if not SETTINGS.offline:
        series = _fetch_yahoo_series(symbol)
        if len(series) >= 2:
            # cycle_date 이하의 마지막 거래일(=결정 종가)의 인덱스
            idx = None
            for i, (d, _) in enumerate(series):
                if d <= cycle_date:
                    idx = i
                else:
                    break
            if idx is not None and idx + 1 < len(series):
                base = series[idx][1]
                nxt = series[idx + 1][1]
                if base:
                    return round((nxt - base) / base * 100.0, 3)
            return None  # 다음 거래일 데이터 아직 없음
    return _synthetic_realized(symbol, cycle_date)

"""시세 데이터 제공자 — Yahoo Finance (무료·API키 불필요).

표준 라이브러리(urllib, json)로 일봉 종가를 수집한다.
같은 프로세스 안에서는 심볼별 전체 시계열을 1회만 받아 캐시한다
(백테스트·시드 시 호출 폭증·레이트리밋 방지).
"""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_CHART_URL = ("https://query1.finance.yahoo.com/v8/finance/chart/"
              "{sym}?range=1y&interval=1d")

# 프로세스 수명 동안 심볼별 (date, close) 시계열 캐시
_SERIES_CACHE: dict[str, list[tuple[str, float]]] = {}


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
    """end_day(포함) 이전 length 거래일의 종가. 실패 시 빈 리스트."""
    series = _fetch_yahoo_series(symbol)
    closes = [c for d, c in series if d <= end_day]
    return closes[-length:] if closes else []


def close_on(symbol: str, target_date: str) -> float | None:
    """target_date(포함) 이하의 마지막 거래일 종가.

    기간별(장기) 예측을 만기 도래 시 실제 종가와 대조하는 데 쓴다.
    target_date 가 아직 미래라 데이터가 없으면 None 을 반환한다.
    """
    series = _fetch_yahoo_series(symbol)
    if not series:
        return None
    last_day = series[-1][0]
    if target_date > last_day:
        return None  # 아직 미래 → 평가 보류
    chosen = None
    for d, c in series:
        if d <= target_date:
            chosen = c
        else:
            break
    return round(chosen, 2) if chosen is not None else None


def price_series(symbol: str, end_day: str | None = None) -> list[tuple[str, float]]:
    """심볼의 (ISO날짜, 종가) 시계열(오름차순). CAR 계산에 사용.

    end_day 지정 시 해당일 이하 거래일만 반환.
    """
    series = _fetch_yahoo_series(symbol)
    if end_day:
        series = [(d, c) for d, c in series if d <= end_day]
    return series


def realized_return_pct(symbol: str, cycle_date: str) -> float | None:
    """cycle_date 에 내린 예측의 실현 수익률(%) = 다음 거래일 종가 변화율.

    다음 거래일 종가가 아직 없으면(미래) None 을 반환하고,
    평가는 그 종목을 건너뛴다(다음에 데이터가 생기면 평가 가능).
    """
    series = _fetch_yahoo_series(symbol)
    if len(series) < 2:
        return None
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

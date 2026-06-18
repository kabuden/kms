"""시세 데이터 제공자.

온라인 모드에서는 yfinance 로 가격을 가져오고, 오프라인이거나
조회 실패 시 결정론적 합성 시계열로 폴백한다. 합성 데이터는
시드가 (심볼, 날짜)로 고정되어 예측→실제 평가가 재현 가능하다.
"""
from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timedelta

from .config import SETTINGS


def _seed(symbol: str, day: str) -> int:
    h = hashlib.sha256(f"{symbol}:{day}".encode()).hexdigest()
    return int(h[:8], 16)


def _synthetic_series(symbol: str, end_day: str, length: int) -> list[float]:
    """end_day 까지 length 거래일의 종가 시계열(합성)."""
    base_seed = _seed(symbol, "base")
    price = 50.0 + (base_seed % 200)
    series: list[float] = []
    d = datetime.fromisoformat(end_day).date() - timedelta(days=length)
    for i in range(length):
        day = (d + timedelta(days=i)).isoformat()
        s = _seed(symbol, day)
        # -1.5% ~ +1.5% 사이의 의사난수 일간 수익률 + 완만한 추세
        daily = ((s % 3000) / 1000.0 - 1.5) / 100.0
        trend = math.sin((base_seed % 100 + i) / 9.0) * 0.004
        price *= (1.0 + daily + trend)
        series.append(round(price, 2))
    return series


def price_history(symbol: str, end_day: str, length: int = 30) -> list[float]:
    """end_day 기준 과거 length 거래일 종가. 실패 시 합성 폴백."""
    if not SETTINGS.offline:
        try:
            import yfinance as yf  # type: ignore

            end = datetime.fromisoformat(end_day).date() + timedelta(days=1)
            start = end - timedelta(days=length * 2 + 10)
            df = yf.download(symbol, start=start.isoformat(),
                             end=end.isoformat(), progress=False)
            closes = [float(x) for x in df["Close"].dropna().tolist()]
            if len(closes) >= 2:
                return closes[-length:]
        except Exception:
            pass
    return _synthetic_series(symbol, end_day, length)


def realized_return_pct(symbol: str, cycle_date: str) -> float:
    """예측이 내려진 cycle_date 다음 거래일의 실현 수익률(%).

    합성 모드에서는 cycle_date 다음날의 일간 수익률을 결정론적으로 계산한다.
    """
    if not SETTINGS.offline:
        try:
            import yfinance as yf  # type: ignore

            start = datetime.fromisoformat(cycle_date).date()
            end = start + timedelta(days=6)
            df = yf.download(symbol, start=start.isoformat(),
                             end=end.isoformat(), progress=False)
            closes = [float(x) for x in df["Close"].dropna().tolist()]
            if len(closes) >= 2:
                return round((closes[1] - closes[0]) / closes[0] * 100.0, 3)
        except Exception:
            pass
    next_day = (datetime.fromisoformat(cycle_date).date() + timedelta(days=1)).isoformat()
    s = _seed(symbol, next_day)
    base = _seed(symbol, "base")
    daily = ((s % 3000) / 1000.0 - 1.5)         # -1.5 ~ +1.5 (%)
    trend = math.sin((base % 100) / 9.0) * 0.4  # 완만한 추세 성분
    return round(daily + trend, 3)

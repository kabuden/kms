"""기간별 목표주가 투영 (projection) 계층.

예측 에이전트들은 단기(다음 거래일) 관점의 기대수익률을 내놓는다. 이 모듈은
그 신호를 받아 여러 기간(다음 종가·주말·1·3·6개월·1년)의 **목표주가 + 수익률 +
방향**을 산출한다. 모델은 다음 두 성분의 합이다.

  1) 단기 알파(predictor 신호): 시간이 지날수록 지수적으로 감쇠(영향이 사라짐)
  2) 역사적 드리프트(과거 일평균 수익률): 기간 길이에 비례해 누적

기간이 길수록 변동성이 커지므로 방향 판단의 flat 밴드는 넓히고 신뢰도는 낮춘다.
외부 의존성 없이 표준 라이브러리만 사용한다.
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

from .config import HORIZONS, Horizon
from .models import to_direction

# 단기 알파 지속성(0~1). 클수록 신호 영향이 오래 남는다. 0.85 → 반감기 ~4거래일.
_ALPHA_PERSISTENCE = 0.85


# ───────────────────────── 날짜 헬퍼 ─────────────────────────
def _as_date(d: str | date) -> date:
    return d if isinstance(d, date) else datetime.fromisoformat(d).date()


def add_business_days(start: str | date, n: int) -> date:
    """start(미포함) 이후 n 거래일(월~금) 뒤 날짜."""
    d = _as_date(start)
    step = 1 if n >= 0 else -1
    remaining = abs(n)
    while remaining > 0:
        d += timedelta(days=step)
        if d.weekday() < 5:
            remaining -= 1
    return d


def business_days_between(start: str | date, end: str | date) -> int:
    """start(미포함)~end(포함) 사이 거래일 수. end 가 이르면 음수."""
    d0, d1 = _as_date(start), _as_date(end)
    if d1 == d0:
        return 0
    step = 1 if d1 > d0 else -1
    d = d0
    count = 0
    while d != d1:
        d += timedelta(days=step)
        if d.weekday() < 5:
            count += step
    return count


def end_of_week(start: str | date) -> date:
    """이번 주 금요일. start 가 이미 금요일 이후면 다음 주 금요일."""
    d = _as_date(start)
    days_to_fri = (4 - d.weekday())  # 금요일=4
    if days_to_fri <= 0:
        days_to_fri += 7
    return d + timedelta(days=days_to_fri)


def add_months(start: str | date, months: int) -> date:
    """달력상 +months. 말일 보정 후, 주말이면 다음 평일로 스냅."""
    d = _as_date(start)
    m = d.month - 1 + months
    year = d.year + m // 12
    month = m % 12 + 1
    # 해당 월의 일수로 클램프
    last_day = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
                else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    day = min(d.day, last_day)
    out = date(year, month, day)
    while out.weekday() >= 5:  # 주말이면 다음 평일
        out += timedelta(days=1)
    return out


def target_date_for(cycle_date: str, horizon: Horizon) -> str:
    if horizon.kind == "bday":
        return add_business_days(cycle_date, horizon.offset).isoformat()
    if horizon.kind == "week":
        return end_of_week(cycle_date).isoformat()
    if horizon.kind == "month":
        return add_months(cycle_date, horizon.offset).isoformat()
    if horizon.kind == "year":
        return add_months(cycle_date, horizon.offset * 12).isoformat()
    raise ValueError(f"unknown horizon kind: {horizon.kind}")


# ───────────────────────── 통계 ─────────────────────────
def _daily_stats(history: list[float]) -> tuple[float, float]:
    """과거 종가 시계열에서 (일평균수익률 mu, 일변동성 sigma)."""
    if not history or len(history) < 3:
        return 0.0, 0.01
    rets = [(history[i] - history[i - 1]) / history[i - 1]
            for i in range(1, len(history)) if history[i - 1]]
    if not rets:
        return 0.0, 0.01
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / len(rets)
    sigma = math.sqrt(var) or 0.01
    return mu, sigma


def _round_price(p: float) -> float:
    """가격대에 맞춘 반올림(원화 대형주는 정수, 그 외 소수 2자리)."""
    if p >= 1000:
        return round(p)
    return round(p, 2)


# ───────────────────────── 투영 ─────────────────────────
def project(cycle_date: str, base_price: float, daily_return_pct: float,
            base_confidence: float, history: list[float]) -> list[dict]:
    """단기 신호를 기간별 목표주가로 투영한다.

    반환: HORIZONS 순서의 dict 리스트. 각 항목:
      horizon, label, target_date, base_price, target_price,
      expected_return_pct, direction, confidence, n_days
    """
    mu, sigma = _daily_stats(history)
    r0 = (daily_return_pct or 0.0) / 100.0
    phi = _ALPHA_PERSISTENCE
    out: list[dict] = []
    for h in HORIZONS:
        tdate = target_date_for(cycle_date, h)
        n = max(1, business_days_between(cycle_date, tdate))
        # 1) 단기 알파: 기하 감쇠 누적합 (n 이 커도 1/(1-phi) 로 수렴 → 폭주 방지)
        alpha_cum = r0 * (1.0 - phi ** n) / (1.0 - phi)
        # 2) 역사적 드리프트: 일평균수익률 × 거래일수
        drift_cum = mu * n
        total = alpha_cum + drift_cum
        target_price = _round_price(base_price * (1.0 + total))
        exp_ret_pct = round(total * 100.0, 2)
        # 기간이 길수록 flat 밴드를 넓혀 잡음을 거른다
        band = max(0.2, sigma * 100.0 * math.sqrt(n) * 0.3)
        direction = to_direction(exp_ret_pct, band)
        # 신뢰도는 기간이 길수록 감쇠
        conf = round(base_confidence / (1.0 + 0.35 * math.log(1 + n)), 3)
        out.append({
            "horizon": h.key, "label": h.label, "target_date": tdate,
            "base_price": _round_price(base_price),
            "target_price": target_price,
            "expected_return_pct": exp_ret_pct,
            "direction": direction, "confidence": conf, "n_days": n,
        })
    return out

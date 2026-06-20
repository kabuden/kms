"""예측 에이전트 #6 — PEAD(실적 발표 후 표류) + 내부자 거래 신호.

이벤트 드리프트 예측기는 두 가지 증거를 결합한다.

① 실적 서프라이즈(PEAD)
  - 실적 발표 당일 기준으로 ±2~15일 창 안에 있으면 신호 발생
  - 서프라이즈 방향(beat/miss)과 역사적 CAR 패턴(avg_car_d5)으로 기대수익률 추정
  - 발표 후 경과일수에 따라 드리프트 감쇠(PEAD는 발표 직후가 가장 강함)

② 내부자 거래(Form 4 SEC / 비예약 매수)
  - CEO·CFO의 비예약(10b5-1 계획 없는) 직접 매수 → 강세 보강
  - 내부자 매도는 단독으로는 약세 신호가 약하므로 실적 신호 없을 때만 적용
  - 10b5-1 예약 거래는 신호로 인정하지 않음

패턴 DB가 비어 있으면(초기 가동) 서프라이즈율에서 단순 비례 추정으로 폴백한다.
"""
from __future__ import annotations

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction

# PEAD 감쇠 계수: 발표 후 N일에서 드리프트의 남은 비율
# 이론: 5일(peak) → 10일(절반) → 15일(거의 소진)
_MAX_DRIFT_DAYS = 14


def _decay(days_since: int) -> float:
    """PEAD 감쇠: 발표 당일(0) = 1.0, MAX_DRIFT_DAYS 이상 = 0.0."""
    if days_since <= 0:
        return 1.0
    if days_since >= _MAX_DRIFT_DAYS:
        return 0.0
    return max(0.0, 1.0 - days_since / _MAX_DRIFT_DAYS)


class EventDriftPredictor(BasePredictor):
    name = "event_drift"
    description = "PEAD(실적 서프라이즈 표류) + 내부자 거래(Form 4) 기반 예측"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        signals: dict = getattr(ctx, "event_signals", None) or {}
        earnings = signals.get("recent_earnings")
        insider = signals.get("recent_insider")

        if not earnings and not insider:
            return self._mk(ctx, 0.0, 0.15, "이벤트 신호 없음")

        er_pct = 0.0
        confidence = 0.20
        parts: list[str] = []

        # ── ① 실적 서프라이즈(PEAD) ──────────────────────────────
        if earnings:
            days_since: int = earnings.get("days_since", 999)
            surprise: float = earnings.get("surprise_pct", 0.0)
            etype: str = earnings.get("event_type", "earnings_unknown")
            d = _decay(days_since)

            car_pattern = earnings.get("historical_car")
            if car_pattern and car_pattern.get("sample_count", 0) >= 3:
                # 패턴 DB 기반: avg_car_d5 × 감쇠
                base_er = car_pattern["avg_car_d5"] * d
                hit_rate = car_pattern.get("hit_rate", 0.55)
                conf_pead = min(0.82, 0.30 + hit_rate * 0.65 * max(d, 0.1))
                n = car_pattern["sample_count"]
                parts.append(
                    f"{etype}({surprise:+.1f}%) D+{days_since}일, "
                    f"역사적D5CAR={car_pattern['avg_car_d5']:+.2f}%(N={n},"
                    f"적중률{hit_rate:.0%})"
                )
            else:
                # 패턴 DB 미보유 → 서프라이즈에서 단순 추정
                # 학술적으로 서프라이즈 10% → D5 CAR ≈ 1.5~2% (전달률 약 15%)
                base_er = surprise * 0.15 * d
                conf_pead = min(0.60, 0.22 + abs(surprise) / 40.0 * d)
                parts.append(
                    f"{etype}({surprise:+.1f}%) D+{days_since}일(패턴미보유)"
                )

            er_pct += base_er
            confidence = max(confidence, conf_pead)

        # ── ② 내부자 거래 신호 ────────────────────────────────────
        if insider:
            txn_type = insider.get("type", "")
            is_scheduled = insider.get("is_scheduled", True)
            role = insider.get("filer_role", "Unknown")
            total_val = insider.get("total_value", 0)
            count = insider.get("count", 1)

            if txn_type == "P" and not is_scheduled:
                # CEO/CFO 비예약 매수 → 가장 강한 강세 신호
                boost = 0.35 if role in ("CEO", "CFO") else 0.18
                boost *= min(1.5, 0.8 + count * 0.2)  # 복수 매수자면 보강
                er_pct += boost
                confidence = min(1.0, confidence + 0.12)
                parts.append(
                    f"내부자매수({role},{count}건,비예약,"
                    f"${total_val:,.0f})"
                )
            elif txn_type == "S" and not is_scheduled and not earnings:
                # 비예약 매도 — 실적 신호 없을 때만 약세 기여
                er_pct -= 0.15
                confidence = min(1.0, confidence + 0.05)
                parts.append(f"내부자매도({role},{count}건,비예약)")

        rationale = "; ".join(parts) or "이벤트 신호 분석"
        return self._mk(ctx, round(er_pct, 3), round(confidence, 3), rationale)

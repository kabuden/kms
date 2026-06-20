"""예측 에이전트 #9 — 저변동성 팩터.

덜 튀는(저변동성) 주식이 위험 대비 장기 수익률이 의외로 높다는
저변동성 이상현상(low-volatility anomaly). 가격 이력만으로 계산되므로
펀더멘털·외부 데이터가 없어도 항상 동작한다.
"""
from __future__ import annotations

from statistics import pstdev

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction


def _daily_vol(history: list[float]) -> float | None:
    """최근 일간 수익률(%)의 표준편차."""
    if not history or len(history) < 4:
        return None
    rets = [(history[i] - history[i - 1]) / history[i - 1] * 100.0
            for i in range(1, len(history)) if history[i - 1]]
    if len(rets) < 3:
        return None
    return pstdev(rets)


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class LowVolatilityPredictor(BasePredictor):
    name = "low_volatility"
    description = "일간 변동성이 낮을수록 위험조정 우위를 신호화 (저변동성 이상현상)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        vol = _daily_vol(ctx.history)
        if vol is None:
            return self._mk(ctx, 0.0, 0.15, "변동성 계산 불가")

        # 일간 변동성 ~1.8% 를 중립으로. 더 잔잔하면(+), 더 출렁이면(-).
        score = _clamp((1.8 - vol) / 1.8)
        expected = round(score * 0.10, 3)  # 가장 약한 신호 → 최대 ±0.1%
        confidence = 0.20 + min(0.20, abs(score) * 0.25)
        label = "저변동" if score > 0 else "고변동"
        rationale = f"{label}(일간변동성 {vol:.2f}%) 변동성점수 {score:+.2f}"
        return self._mk(ctx, expected, round(confidence, 3), rationale)

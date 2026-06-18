"""예측 에이전트 #1 — 기술적 모멘텀.

최근 추세(단기 vs 중기 이동평균, 누적 수익률)가 지속된다고 본다.
"""
from __future__ import annotations

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction


def _sma(values: list[float], n: int) -> float:
    if not values:
        return 0.0
    n = min(n, len(values))
    return sum(values[-n:]) / n


class MomentumPredictor(BasePredictor):
    name = "momentum"
    description = "단기/중기 이동평균과 추세 강도로 방향을 예측 (추세추종)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        h = ctx.history
        if len(h) < 5:
            return self._mk(ctx, 0.0, 0.2, "이력 부족")
        short = _sma(h, 5)
        long = _sma(h, 20)
        spread = (short - long) / long * 100.0 if long else 0.0
        recent = (h[-1] - h[-5]) / h[-5] * 100.0
        # 추세 강도를 다음날 기대수익률로 환산 (감쇠 적용)
        expected = round((spread * 0.25 + recent * 0.15), 3)
        confidence = min(1.0, 0.4 + abs(spread) / 5.0)
        rationale = (f"단기SMA {short:.2f} vs 중기SMA {long:.2f} "
                     f"(괴리 {spread:+.2f}%), 5일 수익률 {recent:+.2f}%")
        return self._mk(ctx, expected, confidence, rationale)

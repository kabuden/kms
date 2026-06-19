"""예측 에이전트 #4 — 평균회귀.

최근 가격이 평균에서 크게 벗어나면 되돌림(반대 방향)을 예측한다.
모멘텀과 의도적으로 상반된 관점을 제공해 앙상블 다양성을 만든다.
"""
from __future__ import annotations

from statistics import mean, pstdev

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction


class MeanReversionPredictor(BasePredictor):
    name = "mean_reversion"
    description = "평균 대비 괴리(z-score)로 되돌림을 예측 (역추세)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        h = ctx.history
        if len(h) < 10:
            return self._mk(ctx, 0.0, 0.2, "이력 부족")
        window = h[-20:]
        mu = mean(window)
        sigma = pstdev(window) or 1e-9
        z = (h[-1] - mu) / sigma
        # z가 양(+)이면 과열 → 하락 예측. 반대 부호로 환산.
        expected = round(-z * 0.4, 3)
        confidence = min(1.0, 0.3 + min(abs(z), 3.0) / 5.0)
        rationale = (f"현재가 {h[-1]:.2f}, 20일평균 {mu:.2f}, "
                     f"z-score {z:+.2f} → 되돌림 기대")
        return self._mk(ctx, expected, confidence, rationale)

"""예측 에이전트 #2 — 뉴스 감성.

해당 시장 경제뉴스의 감성 점수를 종합해 방향을 예측한다.
"""
from __future__ import annotations

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction


class SentimentPredictor(BasePredictor):
    name = "sentiment"
    description = "시장 경제뉴스의 종합 감성 점수로 방향을 예측 (뉴스 기반)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        if not ctx.news:
            return self._mk(ctx, 0.0, 0.2, "뉴스 없음")
        scores = [n.sentiment for n in ctx.news]
        avg = sum(scores) / len(scores)
        # 감성 강도 + 일관성(분산이 작을수록 신뢰↑)
        spread = max(scores) - min(scores)
        expected = round(avg * 1.2, 3)  # 감성 1.0 ≈ +1.2% 기대
        consistency = 1.0 - min(1.0, spread / 2.0)
        confidence = min(1.0, 0.35 + abs(avg) * 0.5 + consistency * 0.2)
        rationale = (f"뉴스 {len(ctx.news)}건 평균감성 {avg:+.3f}, "
                     f"감성범위 {spread:.2f}")
        return self._mk(ctx, expected, confidence, rationale)

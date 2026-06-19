"""예측 에이전트 #3 — 애널리스트 의견 종합.

여러 증권사 등급(매수/중립/매도)과 목표수익률을 가중 종합한다.
"""
from __future__ import annotations

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction

_RATING_WEIGHT = {"buy": 1.0, "hold": 0.0, "sell": -1.0}


class AnalystConsensusPredictor(BasePredictor):
    name = "analyst_consensus"
    description = "증권사 등급/목표가 컨센서스를 종합해 방향을 예측 (펀더멘털 의견)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        views = ctx.analyst_views
        if not views:
            return self._mk(ctx, 0.0, 0.2, "애널리스트 의견 없음")
        rating_score = sum(_RATING_WEIGHT.get(v.rating, 0.0) for v in views) / len(views)
        avg_target = sum(v.target_return_pct for v in views) / len(views)
        # 목표수익률을 다음날 단위로 감쇠(목표는 보통 12개월 기준)
        expected = round(avg_target * 0.05 + rating_score * 0.4, 3)
        buys = sum(1 for v in views if v.rating == "buy")
        sells = sum(1 for v in views if v.rating == "sell")
        agreement = abs(buys - sells) / len(views)
        confidence = min(1.0, 0.4 + agreement * 0.4)
        rationale = (f"{len(views)}개 의견 (매수 {buys}/매도 {sells}), "
                     f"컨센서스 {rating_score:+.2f}, 평균목표 {avg_target:+.2f}%")
        return self._mk(ctx, expected, confidence, rationale)

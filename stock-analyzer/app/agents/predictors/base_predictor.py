"""예측 에이전트 베이스.

각 예측 에이전트는 동일한 입력(시세 이력, 뉴스, 애널리스트 의견)을 받아
서로 다른 방법론으로 종목별 Prediction 을 만든다.
"""
from __future__ import annotations

from abc import abstractmethod

from ...models import AnalystView, NewsItem, Prediction, to_direction
from ..base import Agent


class PredictorContext:
    """예측에 필요한 입력 묶음."""

    def __init__(self, cycle_date: str, symbol: str, market: str,
                 history: list[float], news: list[NewsItem],
                 analyst_views: list[AnalystView]):
        self.cycle_date = cycle_date
        self.symbol = symbol
        self.market = market
        self.history = history
        self.news = news
        self.analyst_views = analyst_views


class BasePredictor(Agent):
    role = "predictor"

    @abstractmethod
    def predict_one(self, ctx: PredictorContext) -> Prediction:
        ...

    def _mk(self, ctx: PredictorContext, expected_return_pct: float,
            confidence: float, rationale: str) -> Prediction:
        confidence = max(0.0, min(1.0, confidence))
        return Prediction(
            cycle_date=ctx.cycle_date, symbol=ctx.symbol, predictor=self.name,
            direction=to_direction(expected_return_pct),
            expected_return_pct=round(expected_return_pct, 3),
            confidence=round(confidence, 3), rationale=rationale,
        )

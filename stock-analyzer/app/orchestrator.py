"""오케스트레이터 — 일일 사이클 조율.

흐름:
  1) 수집 에이전트 2인이 뉴스/애널리스트 의견 수집
  2) 예측 에이전트 5인이 종목별로 각자 예측
  3) 앙상블로 종합 (가중치는 발전 에이전트가 관리)
  4) (다음날) 예측을 실제값과 평가
  5) 발전 에이전트 3인이 가중치/전략/신뢰도를 갱신

'작업 → 결과 평가 → 발전'이 매 사이클 반복되며 정확도/신뢰도가 축적된다.
"""
from __future__ import annotations

from .agents.collectors import KRMarketCollector, USMarketCollector
from .agents.improvers import (
    ConfidenceCalibrator,
    StrategyCritic,
    WeightOptimizer,
)
from .agents.predictors import ALL_PREDICTORS
from .agents.predictors.base_predictor import PredictorContext
from .config import SETTINGS
from .ensemble import combine
from .evaluation import evaluate_cycle
from .market_data import price_history
from .storage import Storage


class Orchestrator:
    def __init__(self, store: Storage):
        self.store = store
        self.collectors = [USMarketCollector(), KRMarketCollector()]
        self.predictors = [cls() for cls in ALL_PREDICTORS]
        self.weight_optimizer = WeightOptimizer()
        self.strategy_critic = StrategyCritic()
        self.confidence_calibrator = ConfidenceCalibrator()

    # ---- 1~3단계: 수집 + 예측 + 앙상블 ----
    def run_predict_cycle(self, cycle_date: str) -> dict:
        # 1) 수집
        news_by_market: dict[str, list] = {}
        for c in self.collectors:
            news = c.collect_news(cycle_date)
            views = c.collect_analyst_views(cycle_date)
            self.store.save_news(cycle_date, news)
            self.store.save_analyst_views(cycle_date, views)
            news_by_market[c.market] = news

        weights = self.store.get_weights()
        params = self.store.get_predictor_params()  # 발전 에이전트가 학습한 보정값
        produced = 0
        ensemble_summary = []

        # 2~3) 종목별 예측 + 앙상블
        for spec in SETTINGS.universe:
            history = price_history(spec.symbol, cycle_date, length=30)
            news = news_by_market.get(spec.market, [])
            views = self.store.analyst_views_for_symbol(cycle_date, spec.symbol)
            ctx = PredictorContext(cycle_date, spec.symbol, spec.market,
                                   history, news, views, params)
            preds = []
            for predictor in self.predictors:
                p = predictor.predict_one(ctx)
                self.store.save_prediction(p)
                preds.append(p)
                produced += 1
            ens = combine(cycle_date, spec.symbol, preds, weights)
            self.store.save_ensemble(ens)
            ensemble_summary.append({
                "symbol": spec.symbol, "name": spec.name,
                "direction": ens.direction,
                "expected_return_pct": ens.expected_return_pct,
                "confidence": ens.confidence,
            })

        return {
            "cycle_date": cycle_date,
            "predictions_made": produced,
            "symbols": len(SETTINGS.universe),
            "ensemble": ensemble_summary,
        }

    # ---- 4~5단계: 평가 + 발전 ----
    def run_evaluate_and_improve(self, cycle_date: str) -> dict:
        eval_result = evaluate_cycle(self.store, cycle_date)

        predictor_names = [p.name for p in self.predictors]
        self.weight_optimizer.run(self.store, cycle_date, predictor_names)
        self.strategy_critic.run(self.store, cycle_date, predictor_names)
        conf = self.confidence_calibrator.run(self.store, cycle_date)

        return {"evaluation": eval_result, "confidence": conf}

    # ---- 편의: 예측 후 즉시 평가/발전 (백테스트/데모용) ----
    def run_full_cycle(self, cycle_date: str) -> dict:
        predict = self.run_predict_cycle(cycle_date)
        improve = self.run_evaluate_and_improve(cycle_date)
        return {"predict": predict, **improve}

    def agent_roster(self) -> dict:
        return {
            "collectors": [a.info() for a in self.collectors],
            "predictors": [a.info() for a in self.predictors],
            "improvers": [
                self.weight_optimizer.info(),
                self.strategy_critic.info(),
                self.confidence_calibrator.info(),
            ],
        }

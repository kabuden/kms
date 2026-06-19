"""오케스트레이터 — 매일 4단계 일일 사이클 조율.

매일 다음 순서로 진행한다.
  1단계) 1차 예측  — 뉴스 제외, 기본 정보(시세·애널리스트)만으로 예측
  2단계) 뉴스 수집·정리 — 미국/한국 경제뉴스 취합
  3단계) 수정 예측  — 뉴스를 반영해 다시 예측(1차 대비 Δ 산출)
  4단계) 장 마감 후 — 수정 예측을 실제와 비교 + 발전 에이전트가 학습

'기본예측 → 뉴스 → 수정예측 → 평가/발전'이 매일 반복되며 정확도/신뢰도가
축적되고, 뉴스가 예측에 미친 효과(수정이 기본보다 나았는지)도 추적한다.
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

    def _predict_stage(self, cycle_date: str, stage: str, news_provider) -> list[dict]:
        """한 단계(기본/수정)의 종목별 예측+앙상블을 수행·저장한다.

        news_provider(spec) -> list[NewsItem] 로 단계별 뉴스 입력을 주입한다
        (baseline=뉴스없음, revised=시장+종목 뉴스).
        """
        weights = self.store.get_weights()
        params = self.store.get_predictor_params()  # 발전 에이전트가 학습한 보정값
        summary = []
        for spec in SETTINGS.universe:
            history = price_history(spec.symbol, cycle_date, length=30)
            news = news_provider(spec)
            views = self.store.analyst_views_for_symbol(cycle_date, spec.symbol)
            ctx = PredictorContext(cycle_date, spec.symbol, spec.market,
                                   history, news, views, params)
            preds = []
            for predictor in self.predictors:
                p = predictor.predict_one(ctx)
                self.store.save_prediction(p, stage=stage)
                preds.append(p)
            ens = combine(cycle_date, spec.symbol, preds, weights)
            self.store.save_ensemble(ens, stage=stage)
            summary.append({
                "symbol": spec.symbol, "name": spec.name,
                "direction": ens.direction,
                "expected_return_pct": ens.expected_return_pct,
                "confidence": ens.confidence,
            })
        return summary

    # ---- 1단계: 1차 예측 (뉴스 제외, 기본 정보만) ----
    def run_phase1_baseline(self, cycle_date: str) -> dict:
        # 애널리스트 의견(기본 정보)은 확보하되, 뉴스는 비운 상태로 예측
        for c in self.collectors:
            self.store.save_analyst_views(cycle_date, c.collect_analyst_views(cycle_date))
        summary = self._predict_stage(cycle_date, "baseline", lambda spec: [])
        return {"stage": "baseline", "ensemble": summary}

    # ---- 2단계: 뉴스 수집·정리 (시장 전반 + 종목별) ----
    def run_phase2_news(self, cycle_date: str) -> dict:
        digest = {}
        collector_by_market = {c.market: c for c in self.collectors}
        for c in self.collectors:
            market_news = c.collect_news(cycle_date)
            self.store.save_news(cycle_date, market_news)
            avg = round(sum(n.sentiment for n in market_news) / len(market_news), 3) \
                if market_news else 0.0
            digest[c.market] = {
                "count": len(market_news), "avg_sentiment": avg,
                "headlines": [{"title": n.title, "sentiment": n.sentiment,
                               "source": n.source} for n in market_news[:6]],
            }
        # 종목별 뉴스
        ticker_total = 0
        for spec in SETTINGS.universe:
            c = collector_by_market.get(spec.market)
            if not c:
                continue
            tn = c.collect_ticker_news(cycle_date, spec)
            if tn:
                self.store.save_news(cycle_date, tn)
                ticker_total += len(tn)
        return {"stage": "news", "digest": digest, "ticker_news": ticker_total}

    # ---- 3단계: 수정 예측 (뉴스 반영, 1차 대비 Δ) ----
    def run_phase3_revised(self, cycle_date: str) -> dict:
        def provider(spec):
            return self.store.news_for_symbol(cycle_date, spec.market, spec.symbol)
        summary = self._predict_stage(cycle_date, "revised", provider)

        # 1차(baseline) 대비 변화량 계산
        base = {e["symbol"]: e for e in
                self.store.ensemble_for_cycle(cycle_date, "baseline")}
        moved = 0
        for row in summary:
            b = base.get(row["symbol"])
            if b:
                row["baseline_return_pct"] = b["expected_return_pct"]
                row["delta_pct"] = round(
                    row["expected_return_pct"] - b["expected_return_pct"], 3)
                row["direction_changed"] = (row["direction"] != b["direction"])
                if row["direction_changed"]:
                    moved += 1
        return {"stage": "revised", "ensemble": summary,
                "direction_changes": moved}

    # ---- 4단계: 장 마감 후 평가 + 발전 ----
    def run_phase4_evaluate(self, cycle_date: str) -> dict:
        eval_result = evaluate_cycle(self.store, cycle_date)
        predictor_names = [p.name for p in self.predictors]
        self.weight_optimizer.run(self.store, cycle_date, predictor_names)
        self.strategy_critic.run(self.store, cycle_date, predictor_names)
        conf = self.confidence_calibrator.run(self.store, cycle_date)
        return {"evaluation": eval_result, "confidence": conf}

    # 하위호환 별칭
    def run_evaluate_and_improve(self, cycle_date: str) -> dict:
        return self.run_phase4_evaluate(cycle_date)

    # ---- 하루 전체(4단계 순차) ----
    def run_full_cycle(self, cycle_date: str) -> dict:
        p1 = self.run_phase1_baseline(cycle_date)
        p2 = self.run_phase2_news(cycle_date)
        p3 = self.run_phase3_revised(cycle_date)
        p4 = self.run_phase4_evaluate(cycle_date)
        return {
            "cycle_date": cycle_date,
            "phase1_baseline": p1,
            "phase2_news": p2,
            "phase3_revised": p3,
            "evaluation": p4["evaluation"],
            "confidence": p4["confidence"],
        }

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

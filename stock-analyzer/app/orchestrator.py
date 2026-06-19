"""오케스트레이터 — 매일 4분석 시점으로 도는 한 사이클을 조율.

한 사이클(거래일 D)은 한국장을 중심으로 4개의 시점으로 진행된다.
  ① 한국장 개장 전 (08:00 KST) — 밤사이 미국장·해외 뉴스로 1차 예측
  ② 한국장 마감 후 (16:00 KST) — 한국장 결과 + 종목 뉴스로 재예측
  ③ 미국장 개장 후 (23:30 KST) — 미국장 흐름 반영 '공식' 예측
  ④ 미국장 마감 후 (06:30 KST D+1) — 실제 종가로 평가 + 발전 + 장기예측 정산

각 예측 시점(①②③)마다 종목별로 5개 예측을 앙상블한 뒤, 그 결과를 여러 기간
(다음 종가·이번 주말·1·3·6개월·1년)의 **목표주가 + 수익률 + 방향**으로 투영해
저장한다. 시점 간 예측이 어떻게 변했는지, 뉴스가 무엇을 바꿨는지, 그리고 실제
주가가 어떻게 움직였는지를 모두 추적한다.

학습(가중치·신뢰도)은 매일 검증 가능한 '다음 거래일 종가'만으로 이뤄지고,
장기 기간 예측은 만기가 도래할 때 실제 종가와 대조해 정확도를 기록한다.
"""
from __future__ import annotations

from statistics import pstdev

from .agents.collectors import KRMarketCollector, USMarketCollector
from .agents.improvers import (
    ConfidenceCalibrator,
    StrategyCritic,
    WeightOptimizer,
)
from .agents.predictors import ALL_PREDICTORS
from .agents.predictors.base_predictor import PredictorContext
from .config import (
    ANALYSIS_POINTS,
    FIRST_PREDICT_POINT,
    OFFICIAL_PREDICT_POINT,
    SETTINGS,
    AnalysisPoint,
)
from .ensemble import combine
from .evaluation import evaluate_cycle, evaluate_due_horizons
from .horizons import project
from .market_data import price_history
from .report import generate_and_store
from .storage import Storage

_POINT_BY_ID = {p.id: p for p in ANALYSIS_POINTS}

# 방향이 ①(개장 전) 대비 ③(공식)에서 뒤집히면 신뢰도에 곱할 감점 계수.
# 시점 간 예측이 흔들렸다는 뜻이라 사전 확신도를 낮춘다.
_FLIP_PENALTY = 0.6


def _volatility(history: list[float]) -> float | None:
    """최근 일간 수익률(%)의 표준편차. 신호 강도 정규화 기준."""
    if not history or len(history) < 3:
        return None
    rets = [(history[i] - history[i - 1]) / history[i - 1] * 100.0
            for i in range(1, len(history)) if history[i - 1]]
    if len(rets) < 2:
        return None
    return pstdev(rets)


class Orchestrator:
    def __init__(self, store: Storage):
        self.store = store
        self.collectors = [USMarketCollector(), KRMarketCollector()]
        self.predictors = [cls() for cls in ALL_PREDICTORS]
        self.weight_optimizer = WeightOptimizer()
        self.strategy_critic = StrategyCritic()
        self.confidence_calibrator = ConfidenceCalibrator()

    # ---- 신규 종목 발견 스캔 ----
    def _scan_discoveries(self, cycle_date: str) -> None:
        """뉴스 헤드라인에서 추적 유니버스 밖의 종목 언급을 감지해 저장."""
        from .ticker_hints import KR_HINTS, US_HINTS
        universe_symbols = {s.symbol for s in SETTINGS.universe}
        all_hints: dict[str, tuple[str, str, list[str]]] = {}
        for sym, (name, kws) in US_HINTS.items():
            all_hints[sym] = (name, "US", kws)
        for sym, (name, kws) in KR_HINTS.items():
            all_hints[sym] = (name, "KR", kws)

        news = self.store.news_for_cycle(cycle_date)
        found: dict[str, int] = {}
        for item in news:
            text = (item.title + " " + (item.summary or "")).lower()
            for sym, (name, market, kws) in all_hints.items():
                if sym in universe_symbols:
                    continue
                if any(kw in text for kw in kws):
                    found[sym] = found.get(sym, 0) + 1
        for sym, count in found.items():
            name, market, _ = all_hints[sym]
            self.store.upsert_discovery(
                sym, name, market, f"뉴스 {count}건 언급 (사이클 {cycle_date})")

    # ---- 뉴스/기본정보 수집 (시점별 정보량 차등) ----
    def _collect_for_point(self, cycle_date: str, point: AnalysisPoint) -> int:
        """시점에 맞는 뉴스를 수집·저장. 반환: 새로 저장한 뉴스 건수."""
        saved = 0
        if point.id == 1:
            # 기본 정보(애널리스트) + 시장 전반(브로드) 뉴스
            for c in self.collectors:
                self.store.save_analyst_views(
                    cycle_date, c.collect_analyst_views(cycle_date))
                market_news = c.collect_news(cycle_date)
                self.store.save_news(cycle_date, market_news)
                saved += len(market_news)
        elif point.id == 2:
            # 종목별(티커) 뉴스 추가
            collector_by_market = {c.market: c for c in self.collectors}
            for spec in SETTINGS.universe:
                c = collector_by_market.get(spec.market)
                if not c:
                    continue
                tn = c.collect_ticker_news(cycle_date, spec)
                if tn:
                    self.store.save_news(cycle_date, tn)
                    saved += len(tn)
        # ③ 미국장 개장 후: ②까지의 뉴스를 재사용(공식 스냅샷)
        return saved

    # ---- 한 예측 시점 실행 (①②③) ----
    def _predict_point(self, cycle_date: str, point: AnalysisPoint) -> dict:
        news_saved = self._collect_for_point(cycle_date, point)
        weights = self.store.get_weights()
        params = self.store.get_predictor_params()
        # ③ 공식 시점: ①(개장 전) 방향과 비교해 전환 여부로 신뢰도 감점
        prior_dir: dict[str, str] = {}
        if point.key == OFFICIAL_PREDICT_POINT:
            prior_dir = {e["symbol"]: e["direction"] for e in
                         self.store.ensemble_for_cycle(
                             cycle_date, FIRST_PREDICT_POINT)}
        summary = []
        for spec in SETTINGS.universe:
            history = price_history(spec.symbol, cycle_date, length=30)
            base_price = history[-1] if history else 0.0
            if point.news_scope == "market":
                news = self.store.news_for_market(cycle_date, spec.market)
            else:
                news = self.store.news_for_symbol(
                    cycle_date, spec.market, spec.symbol)
            views = self.store.analyst_views_for_symbol(cycle_date, spec.symbol)
            ctx = PredictorContext(cycle_date, spec.symbol, spec.market,
                                   history, news, views, params)
            preds = []
            for predictor in self.predictors:
                p = predictor.predict_one(ctx)
                self.store.save_prediction(p, stage=point.key,
                                           analysis_point=point.id,
                                           base_price=base_price)
                preds.append(p)
            ens = combine(cycle_date, spec.symbol, preds, weights,
                          volatility=_volatility(history))
            # 시점 간 방향 전환 → 사전 확신도 감점
            pd = prior_dir.get(spec.symbol)
            if pd and pd != ens.direction:
                ens.confidence = round(ens.confidence * _FLIP_PENALTY, 3)
            self.store.save_ensemble(ens, stage=point.key,
                                     analysis_point=point.id,
                                     base_price=base_price)
            # 앙상블 신호를 기간별 목표주가로 투영
            targets = project(cycle_date, base_price, ens.expected_return_pct,
                              ens.confidence, history)
            self.store.save_horizon_targets(cycle_date, point.id, spec.symbol,
                                            "ensemble", targets)
            summary.append({
                "symbol": spec.symbol, "name": spec.name,
                "direction": ens.direction,
                "expected_return_pct": ens.expected_return_pct,
                "confidence": ens.confidence, "base_price": base_price,
            })
        self._scan_discoveries(cycle_date)
        return {"point": point.id, "key": point.key, "label": point.label,
                "news_saved": news_saved, "ensemble": summary}

    # ---- ④ 평가 + 발전 + 장기예측 정산 ----
    def run_phase4_evaluate(self, cycle_date: str) -> dict:
        eval_result = evaluate_cycle(self.store, cycle_date)
        predictor_names = [p.name for p in self.predictors]
        self.weight_optimizer.run(self.store, cycle_date, predictor_names)
        self.strategy_critic.run(self.store, cycle_date, predictor_names)
        conf = self.confidence_calibrator.run(self.store, cycle_date)
        # 만기 도래한 장기 기간 예측을 실제 종가로 정산(학습엔 미반영)
        horizon_eval = evaluate_due_horizons(self.store, cycle_date)
        # 사이클 마감 리포트 생성·저장
        report = generate_and_store(self.store, cycle_date)
        return {"evaluation": eval_result, "confidence": conf,
                "horizon_settlement": horizon_eval,
                "report_summary": report["summary"]}

    # ---- 시점 디스패처 (스케줄러·웹에서 호출) ----
    def run_analysis_point(self, cycle_date: str, point_id: int) -> dict:
        point = _POINT_BY_ID.get(point_id)
        if not point:
            raise ValueError(f"unknown analysis point: {point_id}")
        if point.role == "evaluate":
            return self.run_phase4_evaluate(cycle_date)
        return self._predict_point(cycle_date, point)

    # ---- 하위호환 별칭 (기존 호출부 유지) ----
    def run_phase1_baseline(self, cycle_date: str) -> dict:
        return self.run_analysis_point(cycle_date, 1)

    def run_phase2_news(self, cycle_date: str) -> dict:
        return self.run_analysis_point(cycle_date, 2)

    def run_phase3_revised(self, cycle_date: str) -> dict:
        return self.run_analysis_point(cycle_date, 3)

    def run_evaluate_and_improve(self, cycle_date: str) -> dict:
        return self.run_phase4_evaluate(cycle_date)

    # ---- 하루 전체(4시점 순차) ----
    def run_full_cycle(self, cycle_date: str) -> dict:
        points = {}
        for point in ANALYSIS_POINTS:
            if point.role == "predict":
                points[point.key] = self._predict_point(cycle_date, point)
        p4 = self.run_phase4_evaluate(cycle_date)
        return {
            "cycle_date": cycle_date,
            "points": points,
            "evaluation": p4["evaluation"],
            "confidence": p4["confidence"],
            "horizon_settlement": p4["horizon_settlement"],
            "report_summary": p4["report_summary"],
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

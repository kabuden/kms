"""예측 vs 실제 평가.

각 사이클의 예측에 대해 다음 거래일 실현 수익률을 받아와
개별 예측 에이전트와 앙상블의 적중 여부/오차를 기록한다.
"""
from __future__ import annotations

from .market_data import realized_return_pct
from .models import Actual, Evaluation, to_direction
from .storage import Storage

ENSEMBLE_KEY = "__ensemble__"


def evaluate_cycle(store: Storage, cycle_date: str) -> dict:
    """cycle_date 예측들을 실제값과 대조해 평가를 적재한다."""
    preds = store.predictions_for_cycle(cycle_date)
    ensembles = store.ensemble_for_cycle(cycle_date)
    symbols = {p.symbol for p in preds} | {e["symbol"] for e in ensembles}

    evaluated = 0
    ensemble_hits = 0
    ensemble_total = 0

    # 종목별 실제 수익률 확보
    actuals: dict[str, float] = {}
    for symbol in symbols:
        cached = store.actual(cycle_date, symbol)
        if cached is None:
            cached = realized_return_pct(symbol, cycle_date)
            store.save_actual(Actual(cycle_date, symbol, cached))
        actuals[symbol] = cached

    # 개별 예측 평가
    for p in preds:
        actual = actuals[p.symbol]
        actual_dir = to_direction(actual)
        hit = (p.direction == actual_dir)
        store.save_evaluation(Evaluation(
            cycle_date, p.symbol, p.predictor, p.direction, actual_dir,
            hit, abs(p.expected_return_pct - actual),
        ))
        evaluated += 1

    # 앙상블 평가
    for e in ensembles:
        actual = actuals[e["symbol"]]
        actual_dir = to_direction(actual)
        hit = (e["direction"] == actual_dir)
        store.save_evaluation(Evaluation(
            cycle_date, e["symbol"], ENSEMBLE_KEY, e["direction"], actual_dir,
            hit, abs(e["expected_return_pct"] - actual),
        ))
        ensemble_total += 1
        ensemble_hits += int(hit)

    return {
        "cycle_date": cycle_date,
        "evaluated_predictions": evaluated,
        "ensemble_hits": ensemble_hits,
        "ensemble_total": ensemble_total,
        "ensemble_accuracy": round(ensemble_hits / ensemble_total, 3)
        if ensemble_total else None,
    }

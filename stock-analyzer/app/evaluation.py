"""예측 vs 실제 평가.

각 사이클의 예측에 대해 다음 거래일 실현 수익률을 받아와
개별 예측 에이전트와 앙상블의 적중 여부/오차를 기록한다.
"""
from __future__ import annotations

from .market_data import realized_return_pct
from .models import Actual, Evaluation, to_direction
from .storage import Storage

ENSEMBLE_KEY = "__ensemble__"           # 공식 기록: 수정(뉴스반영) 앙상블
ENSEMBLE_BASELINE_KEY = "__ensemble_baseline__"  # 비교용: 1차(기본) 앙상블


def evaluate_cycle(store: Storage, cycle_date: str) -> dict:
    """cycle_date 의 수정 예측을 실제값과 대조해 평가를 적재한다.

    - 개별 예측가/수정 앙상블: 공식 성과로 기록(발전 에이전트 학습에 사용)
    - 1차(기본) 앙상블: 별도 키로 기록해 '뉴스 반영 효과'를 비교
    """
    preds = store.predictions_for_cycle(cycle_date, "revised")
    revised = store.ensemble_for_cycle(cycle_date, "revised")
    baseline = store.ensemble_for_cycle(cycle_date, "baseline")
    symbols = {p.symbol for p in preds} | {e["symbol"] for e in revised}

    # 종목별 실제 수익률 확보. 실데이터에서 다음 거래일 종가가 아직 없으면
    # (미래) None → 그 종목은 이번 평가에서 건너뛴다.
    actuals: dict[str, float] = {}
    for symbol in symbols:
        cached = store.actual(cycle_date, symbol)
        if cached is None:
            cached = realized_return_pct(symbol, cycle_date)
            if cached is None:
                continue
            store.save_actual(Actual(cycle_date, symbol, cached))
        actuals[symbol] = cached

    # 개별 예측가 평가(수정 예측 기준)
    evaluated = 0
    for p in preds:
        if p.symbol not in actuals:
            continue
        actual_dir = to_direction(actuals[p.symbol])
        store.save_evaluation(Evaluation(
            cycle_date, p.symbol, p.predictor, p.direction, actual_dir,
            p.direction == actual_dir, abs(p.expected_return_pct - actuals[p.symbol]),
        ))
        evaluated += 1

    def _eval_ensemble(rows, key) -> tuple[int, int]:
        hits = count = 0
        for e in rows:
            if e["symbol"] not in actuals:
                continue
            actual_dir = to_direction(actuals[e["symbol"]])
            hit = (e["direction"] == actual_dir)
            store.save_evaluation(Evaluation(
                cycle_date, e["symbol"], key, e["direction"], actual_dir,
                hit, abs(e["expected_return_pct"] - actuals[e["symbol"]]),
            ))
            hits += int(hit)
            count += 1
        return hits, count

    ensemble_hits, total = _eval_ensemble(revised, ENSEMBLE_KEY)
    baseline_hits, base_total = _eval_ensemble(baseline, ENSEMBLE_BASELINE_KEY)

    return {
        "cycle_date": cycle_date,
        "evaluated_predictions": evaluated,
        "ensemble_hits": ensemble_hits,
        "ensemble_total": total,
        "ensemble_accuracy": round(ensemble_hits / total, 3) if total else None,
        "baseline_hits": baseline_hits,
        "baseline_accuracy": round(baseline_hits / base_total, 3)
        if base_total else None,
        "news_helped": (ensemble_hits - baseline_hits) if base_total else None,
    }

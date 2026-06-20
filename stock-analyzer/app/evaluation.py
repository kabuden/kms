"""예측 vs 실제 평가.

각 사이클의 예측에 대해 다음 거래일 실현 수익률을 받아와
개별 예측 에이전트와 앙상블의 적중 여부/오차를 기록한다(학습 신호).

또한 만기가 도래한 장기 기간 예측(주말·1·3·6개월·1년)을 실제 종가와
대조해 정확도를 기록한다(표시·추적용, 학습엔 미반영).
"""
from __future__ import annotations

from .config import FIRST_PREDICT_POINT, OFFICIAL_PREDICT_POINT
from .market_data import close_on, realized_return_pct
from .models import Actual, Evaluation, to_direction
from .storage import Storage

ENSEMBLE_KEY = "__ensemble__"           # 공식 기록: 공식(미국개장후) 앙상블
ENSEMBLE_BASELINE_KEY = "__ensemble_baseline__"  # 비교용: 최초(한국개장전) 앙상블

# 정확도 지수 분모 하한(%p). 실제 변동이 미세할 때 상대오차가 폭발하는 것을 막는다.
_ACC_MIN_DENOM = 0.5


def magnitude_accuracy(predicted_pct: float, actual_pct: float,
                       min_denom: float = _ACC_MIN_DENOM) -> float:
    """크기를 고려한 정확도 지수(0~1).

    절대 오차가 같아도 예측·실제의 크기가 크면 더 정확한 것으로 본다.
    예) 예측 +20%/실제 +19.9% → 0.995, 예측 +2%/실제 +1.9% → 0.95
    (둘 다 절대오차 0.1%p지만 상대적으로 전자가 훨씬 정밀).
    방향이 반대면 상대오차가 커져 자연히 0에 수렴한다.
    """
    denom = max(abs(actual_pct), abs(predicted_pct), min_denom)
    rel_err = abs(predicted_pct - actual_pct) / denom
    return round(max(0.0, 1.0 - rel_err), 3)



def evaluate_cycle(store: Storage, cycle_date: str) -> dict:
    """cycle_date 의 공식 예측을 다음 거래일 종가와 대조해 평가를 적재한다.

    - 개별 예측가/공식 앙상블: 공식 성과로 기록(발전 에이전트 학습에 사용)
    - 최초(한국개장전) 앙상블: 별도 키로 기록해 '시점 경과에 따른 정보 반영
      효과'(개장전 → 미국개장후)를 비교
    """
    preds = store.predictions_for_cycle(cycle_date, OFFICIAL_PREDICT_POINT)
    revised = store.ensemble_for_cycle(cycle_date, OFFICIAL_PREDICT_POINT)
    baseline = store.ensemble_for_cycle(cycle_date, FIRST_PREDICT_POINT)
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


def evaluate_due_horizons(store: Storage, today: str) -> dict:
    """만기(target_date<=today)가 도래한 장기 기간 예측을 실제 종가로 정산한다.

    - 방향 적중 여부와 가격오차(기준가 대비 %)를 horizon_targets 에 기록한다.
    - 학습(가중치·신뢰도)에는 반영하지 않는다(표시·추적 전용).
    """
    pending = store.pending_horizon_targets(today)
    settled = 0
    for t in pending:
        actual = close_on(t["symbol"], t["target_date"])
        if actual is None:
            continue  # 아직 해당 거래일 데이터 없음 → 다음에 정산
        base = t["base_price"] or 0.0
        if base:
            actual_ret = (actual - base) / base * 100.0
            abs_err = abs(t["target_price"] - actual) / base * 100.0
        else:
            actual_ret = 0.0
            abs_err = abs(t["target_price"] - actual)
        actual_dir = to_direction(actual_ret)
        hit = (t["direction"] == actual_dir)
        store.update_horizon_actual(t["id"], round(actual, 2), hit,
                                    round(abs_err, 3))
        settled += 1
    return {"checked": len(pending), "settled": settled}

"""5개 예측 에이전트의 결과를 가중 종합해 최종 예측을 만든다.

가중치는 발전 에이전트(weight_optimizer)가 과거 정확도로 갱신한다.
"""
from __future__ import annotations

from .models import EnsemblePrediction, Prediction, to_direction


def combine(cycle_date: str, symbol: str, preds: list[Prediction],
            weights: dict[str, float]) -> EnsemblePrediction:
    if not preds:
        return EnsemblePrediction(cycle_date, symbol, "flat", 0.0, 0.0)

    # 가중치 × 개별 신뢰도로 기대수익률 가중평균
    num = 0.0
    den = 0.0
    contributors: dict[str, str] = {}
    used_weights: dict[str, float] = {}
    # 방향별 가중 투표: 평균이 flat 밴드로 희석되는 것을 막는다.
    dir_votes: dict[str, float] = {"up": 0.0, "down": 0.0, "flat": 0.0}
    for p in preds:
        w = weights.get(p.predictor, 1.0)
        eff = w * (0.5 + 0.5 * p.confidence)  # 신뢰 높은 예측에 더 무게
        num += eff * p.expected_return_pct
        den += eff
        dir_votes[p.direction] += eff
        contributors[p.predictor] = p.direction
        used_weights[p.predictor] = round(w, 3)

    expected = round(num / den, 3) if den else 0.0
    # 방향은 가중 투표로 결정(동률이면 기대수익률 부호로 보강)
    direction = max(dir_votes, key=dir_votes.get)
    if dir_votes["up"] == dir_votes["down"] and dir_votes["up"] > 0:
        direction = to_direction(expected)

    # 합의도: 최종 방향에 투표한 가중 비율
    total_w = sum(dir_votes.values()) or 1e-9
    agreement = dir_votes[direction] / total_w
    avg_conf = sum(p.confidence for p in preds) / len(preds)
    confidence = round(min(1.0, 0.5 * agreement + 0.5 * avg_conf), 3)

    return EnsemblePrediction(
        cycle_date=cycle_date, symbol=symbol, direction=direction,
        expected_return_pct=expected, confidence=confidence,
        weights=used_weights, contributors=contributors,
    )

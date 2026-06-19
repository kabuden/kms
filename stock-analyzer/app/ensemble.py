"""5개 예측 에이전트의 결과를 가중 종합해 최종 예측을 만든다.

가중치는 발전 에이전트(weight_optimizer)가 과거 정확도로 갱신한다.

신뢰도(confidence)는 '예측이 맞을 가능성에 대한 사전(事前) 확신도'다.
실제 결과가 나오기 전에 산출되므로 그 예측 자신의 오차로는 정의될 수 없고,
대신 세 가지 사전 신호로 산정한다.
  1) 방향 합의도(consensus): 5개 에이전트가 같은 방향에 얼마나 모였나.
     반반(50:50)이면 0, 만장일치면 1. → 방향이 갈리면 신뢰가 급감한다.
  2) 신호 강도(strength): 기대수익률이 그 종목의 일반 변동성 대비 얼마나 큰가.
     변동성 안에 묻히는 미세한 신호는 약하게 본다.
  3) 크기 일관성(coherence): 5개 예측의 기대수익률이 서로 얼마나 모이나.
합의도를 게이트(곱)로 두어, 합의가 없으면 강한 신호라도 신뢰를 낮게 잡는다.
"""
from __future__ import annotations

from statistics import pstdev

from .models import EnsemblePrediction, Prediction, to_direction


def _confidence(preds: list[Prediction], dir_votes: dict[str, float],
                direction: str, expected: float,
                volatility: float | None) -> float:
    total_w = sum(dir_votes.values()) or 1e-9
    vote_share = dir_votes[direction] / total_w
    # 1) 방향 합의도: 반반(0.5)→0, 만장일치(1.0)→1
    consensus = max(0.0, (vote_share - 0.5) / 0.5)
    # 2) 신호 강도: 변동성 대비 기대수익 크기(변동성 모르면 1%p 기준)
    scale = volatility if (volatility and volatility > 1e-6) else 1.0
    strength = min(1.0, abs(expected) / scale)
    # 3) 크기 일관성: 예측 분산이 작을수록 ↑
    exp_vals = [p.expected_return_pct for p in preds]
    disp = pstdev(exp_vals) if len(exp_vals) > 1 else 0.0
    coherence = 1.0 / (1.0 + disp)
    # 합의도를 게이트로: 합의가 없으면 강도가 커도 신뢰 낮음
    score = consensus * (0.55 + 0.30 * strength + 0.15 * coherence)
    return round(max(0.0, min(1.0, score)), 3)


def combine(cycle_date: str, symbol: str, preds: list[Prediction],
            weights: dict[str, float],
            volatility: float | None = None) -> EnsemblePrediction:
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

    confidence = _confidence(preds, dir_votes, direction, expected, volatility)

    return EnsemblePrediction(
        cycle_date=cycle_date, symbol=symbol, direction=direction,
        expected_return_pct=expected, confidence=confidence,
        weights=used_weights, contributors=contributors,
    )


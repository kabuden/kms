"""예측 에이전트 #8 — 퀄리티 팩터.

고ROE·저부채·높은 이익률 기업이 장기적으로 아웃퍼폼한다는 퀄리티 프리미엄.
파마-프렌치 RMW(Robust-minus-Weak) 수익성 팩터의 단순화 버전.
"""
from __future__ import annotations

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class QualityPredictor(BasePredictor):
    name = "quality"
    description = "ROE·부채비율·이익률로 기업 체력을 신호화 (퀄리티 팩터)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        f: dict = getattr(ctx, "fundamentals", None) or {}
        roe = f.get("roe")
        de = f.get("debt_to_equity")          # 야후: % 단위 (150 = 1.5배)
        margin = f.get("profit_margin")

        scores: list[float] = []
        parts: list[str] = []
        # ROE: 12% 중립, 32%+ 만점
        if roe is not None:
            scores.append(_clamp((roe - 0.12) / 0.20))
            parts.append(f"ROE {roe * 100:.0f}%")
        # 부채비율: 0 → +1, 2배(200%) → -1
        if de is not None:
            de_ratio = de / 100.0
            scores.append(_clamp((1.0 - de_ratio) / 1.0))
            parts.append(f"부채/자본 {de_ratio:.1f}x")
        # 순이익률: 20%+ 만점
        if margin is not None:
            scores.append(_clamp(margin / 0.20))
            parts.append(f"이익률 {margin * 100:.0f}%")

        if not scores:
            return self._mk(ctx, 0.0, 0.15, "퀄리티 지표 없음")

        score = sum(scores) / len(scores)
        expected = round(score * 0.25, 3)  # 강한 우량 → 최대 ±0.25%
        confidence = 0.22 + min(0.30, abs(score) * 0.35) * (len(scores) / 3.0)
        label = "우량" if score > 0 else "취약"
        rationale = f"{label}({', '.join(parts)}) 퀄리티점수 {score:+.2f}"
        return self._mk(ctx, expected, round(confidence, 3), rationale)

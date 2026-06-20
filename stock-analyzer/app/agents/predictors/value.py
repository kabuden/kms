"""예측 에이전트 #7 — 밸류 팩터.

저평가(낮은 PER·PBR·PSR) 주식이 장기적으로 초과수익을 낸다는 가치 프리미엄.
파마-프렌치 HML(High-minus-Low) 팩터의 단순화 버전.

밸류는 느린 신호라 일간 기대수익률 기여는 작게 잡되, 매우 싸거나 매우 비싼
경우엔 flat 밴드(±0.2%)를 넘도록 스케일을 둔다.
"""
from __future__ import annotations

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class ValuePredictor(BasePredictor):
    name = "value"
    description = "PER·PBR·PSR 저평가 정도로 가치 프리미엄을 신호화 (밸류 팩터)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        f: dict = getattr(ctx, "fundamentals", None) or {}
        pe = f.get("pe")
        pb = f.get("pb")
        ps = f.get("ps")

        scores: list[float] = []
        parts: list[str] = []
        # PER: 적정 ~18 기준. 싸면(+), 비싸면(-). 적자(PER<=0)는 제외.
        if pe is not None and pe > 0:
            scores.append(_clamp((18.0 - pe) / 18.0))
            parts.append(f"PER {pe:.1f}")
        # PBR: 적정 ~2.5
        if pb is not None and pb > 0:
            scores.append(_clamp((2.5 - pb) / 2.5))
            parts.append(f"PBR {pb:.2f}")
        # PSR: 적정 ~2.0
        if ps is not None and ps > 0:
            scores.append(_clamp((2.0 - ps) / 2.0))
            parts.append(f"PSR {ps:.2f}")

        if not scores:
            return self._mk(ctx, 0.0, 0.15, "밸류 지표 없음")

        score = sum(scores) / len(scores)
        expected = round(score * 0.30, 3)  # 강한 저평가 → 최대 ±0.3%
        # 신뢰도: 지표 충실도 + 신호 강도
        confidence = 0.22 + min(0.30, abs(score) * 0.35) * (len(scores) / 3.0)
        label = "저평가" if score > 0 else "고평가"
        rationale = f"{label}({', '.join(parts)}) 밸류점수 {score:+.2f}"
        return self._mk(ctx, expected, round(confidence, 3), rationale)

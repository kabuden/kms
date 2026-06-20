"""예측 에이전트 #10 — 섹터 전이 효과.

같은 섹터 동료 종목의 실적 서프라이즈가 종목 전체로 파급되는 현상.
예: NVDA가 어닝 비트하면 같은 반도체인 LRCX·SNDK도 동반 강세를 보이는 경향.

자기 자신의 실적은 event_drift 가 담당하므로, 여기서는 '동료의' 실적만 본다
(중복 신호 방지). 동료의 서프라이즈 × 전이계수 × 경과일 감쇠로 추정한다.
"""
from __future__ import annotations

from .base_predictor import BasePredictor, PredictorContext
from ...models import Prediction

# 전이는 본인 실적보다 약하다(전달률 ~5%). 발표 후 3일이면 거의 소진.
_SPILLOVER_RATE = 0.05
_MAX_SPILLOVER_DAYS = 3


def _decay(days_since: int) -> float:
    if days_since <= 0:
        return 1.0
    if days_since >= _MAX_SPILLOVER_DAYS:
        return 0.0
    return max(0.0, 1.0 - days_since / _MAX_SPILLOVER_DAYS)


class SectorSpilloverPredictor(BasePredictor):
    name = "sector_spillover"
    description = "같은 섹터 동료의 실적 서프라이즈 파급을 신호화 (섹터 전이)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        signals: dict = getattr(ctx, "sector_signals", None) or {}
        peers: list[dict] = signals.get("peer_events", [])
        if not peers:
            return self._mk(ctx, 0.0, 0.15, "동료 실적 이벤트 없음")

        contributions: list[float] = []
        parts: list[str] = []
        for ev in peers:
            surprise = ev.get("surprise_pct") or 0.0
            days = ev.get("days_since", 99)
            d = _decay(days)
            if d <= 0 or surprise == 0:
                continue
            contributions.append(surprise * _SPILLOVER_RATE * d)
            parts.append(
                f"{ev.get('symbol', '?')} {ev.get('event_type', '')}"
                f"({surprise:+.0f}%,D+{days})")

        if not contributions:
            return self._mk(ctx, 0.0, 0.15, "유효 전이 신호 없음")

        # 동료들의 전이를 합산하되 과대평가 방지를 위해 ±1.0% 로 제한
        expected = max(-1.0, min(1.0, sum(contributions)))
        n = len(contributions)
        confidence = min(0.65, 0.25 + n * 0.12 + abs(expected) * 0.15)
        rationale = f"섹터 전이 {', '.join(parts)} → {expected:+.2f}%"
        return self._mk(ctx, round(expected, 3), round(confidence, 3), rationale)

"""발전 에이전트 #2 — 전략 비평.

어떤 예측 에이전트가 부진한지 진단하고, 개선 방향을 로그로 남긴다.
지속적으로 랜덤(0.5)보다 못한 에이전트는 '검토 필요'로 표시한다.
"""
from __future__ import annotations

from ...config import SETTINGS
from ...storage import Storage
from ..base import Agent


class StrategyCritic(Agent):
    name = "strategy_critic"
    role = "improver"
    description = "부진한 예측 에이전트를 진단하고 개선 방향을 제시"

    def run(self, store: Storage, cycle_date: str, predictor_names: list[str]) -> None:
        window = SETTINGS.rolling_window
        verdicts = []
        for name in predictor_names:
            hits, total = store.predictor_accuracy(name, window)
            if total < 3:
                verdicts.append(f"{name}: 표본부족({total})")
                continue
            acc = hits / total
            if acc < 0.45:
                advice = "지속 부진 → 가중치 축소 또는 로직 재검토 권고"
            elif acc < 0.5:
                advice = "랜덤 이하 → 신호 임계값 조정 검토"
            elif acc >= 0.6:
                advice = "우수 → 가중치 확대 후보"
            else:
                advice = "보통"
            verdicts.append(f"{name}: {acc:.2f} {advice}")

        # 최고/최저 성과자 식별
        ranked = []
        for name in predictor_names:
            hits, total = store.predictor_accuracy(name, window)
            if total >= 3:
                ranked.append((hits / total, name))
        headline = ""
        if ranked:
            ranked.sort(reverse=True)
            best = ranked[0]
            worst = ranked[-1]
            headline = (f"최고: {best[1]}({best[0]:.2f}), "
                        f"최저: {worst[1]}({worst[0]:.2f}). ")

        store.log_improver(
            cycle_date, self.name, "critique", headline + " | ".join(verdicts),
        )

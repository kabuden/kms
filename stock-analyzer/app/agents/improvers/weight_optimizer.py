"""발전 에이전트 #1 — 가중치 최적화.

각 예측 에이전트의 최근 적중률(rolling accuracy)에 비례해 앙상블
가중치를 재배분한다. 잘 맞히는 에이전트의 영향력을 키운다.
"""
from __future__ import annotations

from ...config import SETTINGS
from ...storage import Storage
from ..base import Agent


class WeightOptimizer(Agent):
    name = "weight_optimizer"
    role = "improver"
    description = "최근 적중률에 비례해 예측 에이전트 가중치를 재배분"

    def run(self, store: Storage, cycle_date: str, predictor_names: list[str]) -> None:
        window = SETTINGS.rolling_window
        scores: dict[str, float] = {}
        details = []
        for name in predictor_names:
            hits, total = store.predictor_accuracy(name, window)
            # 평가 데이터가 없으면 중립(0.5)
            acc = hits / total if total else 0.5
            # 0.5(랜덤) 기준으로 보상. 0.5 미만이면 가중치를 낮춤.
            score = max(0.1, 0.5 + (acc - 0.5) * 2.0)
            scores[name] = score
            details.append(f"{name}={acc:.2f}({hits}/{total})")

        total_score = sum(scores.values()) or 1e-9
        for name, sc in scores.items():
            # 평균 1.0 이 되도록 정규화
            weight = round(sc / total_score * len(scores), 3)
            store.set_weight(name, weight)

        store.log_improver(
            cycle_date, self.name, "reweight",
            "적중률 기반 가중치 갱신 | " + ", ".join(details),
        )

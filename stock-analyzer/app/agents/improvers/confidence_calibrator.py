"""발전 에이전트 #3 — 신뢰도 보정 및 실거래 게이트.

앙상블의 전체/롤링 적중률을 추적해 '보정 신뢰도'를 산출하고,
충분한 사이클 수와 정확도 기준을 만족하면 trade_ready 플래그를 켠다.
이 플래그가 켜지기 전까지는 실제 투자 사용을 권하지 않는다.
"""
from __future__ import annotations

from ...config import SETTINGS
from ...storage import Storage
from ..base import Agent

ENSEMBLE_KEY = "__ensemble__"


class ConfidenceCalibrator(Agent):
    name = "confidence_calibrator"
    role = "improver"
    description = "앙상블 정확도를 추적해 신뢰도를 보정하고 실거래 가능 여부를 판정"

    def run(self, store: Storage, cycle_date: str) -> dict:
        overall_hits, overall_total = store.predictor_accuracy(ENSEMBLE_KEY)
        roll_hits, roll_total = store.predictor_accuracy(
            ENSEMBLE_KEY, SETTINGS.rolling_window)

        overall_acc = overall_hits / overall_total if overall_total else 0.0
        rolling_acc = roll_hits / roll_total if roll_total else 0.0

        n_cycles = len(store.cycle_dates())
        # 표본이 적을수록 신뢰도를 깎는 축소(shrinkage) 계수
        sample_factor = min(1.0, n_cycles / max(1, SETTINGS.min_cycles_for_trust))
        calibrated = round(rolling_acc * sample_factor, 3)

        trade_ready = (
            n_cycles >= SETTINGS.min_cycles_for_trust
            and rolling_acc >= SETTINGS.min_accuracy_for_trust
            and overall_total >= SETTINGS.min_cycles_for_trust
        )

        detail = (
            f"사이클 {n_cycles}/{SETTINGS.min_cycles_for_trust}, "
            f"전체정확도 {overall_acc:.2f}, 롤링정확도 {rolling_acc:.2f}, "
            f"기준 {SETTINGS.min_accuracy_for_trust:.2f} → "
            f"{'실거래 가능' if trade_ready else '학습/검증 단계'}"
        )

        store.save_confidence(cycle_date, round(overall_acc, 3),
                              round(rolling_acc, 3), calibrated,
                              trade_ready, detail)
        store.log_improver(cycle_date, self.name, "calibrate", detail)
        return {
            "overall_accuracy": round(overall_acc, 3),
            "rolling_accuracy": round(rolling_acc, 3),
            "calibrated_confidence": calibrated,
            "trade_ready": trade_ready,
            "n_cycles": n_cycles,
            "detail": detail,
        }

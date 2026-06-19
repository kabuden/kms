"""발전 에이전트 #2 — 전략 비평 + 예측가 자가개선.

매 사이클 각 예측 에이전트의 최근 성과를 보고 **실제로 로직을 보정**한다.
적중도를 끌어올리기 위해 두 가지를 학습한다.

  1) 부호(sign) 학습 — 어떤 예측가가 지속적으로 반대로 맞히면(반예측적)
     신호를 자동 반전시켜 적중도를 회복한다. (0.42~0.58 구간은 데드존: 잦은
     반전을 막는 히스테리시스)
  2) 크기(scale) 보정 — 예측 변동폭이 실제 변동폭과 어긋나면 게인을 조정해
     기대수익률의 스케일을 실제에 맞춘다(완만한 지수평활).

비평 결과와 보정 내역을 모두 로그로 남긴다.
"""
from __future__ import annotations

from statistics import mean

from ...config import OFFICIAL_PREDICT_POINT, SETTINGS
from ...storage import Storage
from ..base import Agent

# 3분류(상승/하락/보합)에서 무작위 적중률은 ~0.40 이므로, 그 잡음 밴드보다
# 분명히 낮을 때만 '반예측적'으로 보고 반전한다(노이즈에 흔들리지 않게).
FLIP_THRESHOLD = 0.35
SCALE_MIN, SCALE_MAX = 0.3, 3.0
SCALE_SMOOTH = 0.3         # 새 목표를 반영하는 비율(나머지는 기존 유지)


class StrategyCritic(Agent):
    name = "strategy_critic"
    role = "improver"
    description = "예측가 성과를 진단하고 부호·스케일을 자가보정해 적중도를 개선"

    def run(self, store: Storage, cycle_date: str, predictor_names: list[str]) -> None:
        window = SETTINGS.rolling_window
        meta = store.get_predictor_meta()
        verdicts = []
        changes = []
        ranked = []

        for name in predictor_names:
            hits, total = store.predictor_accuracy(name, window)
            m = meta.get(name, {"scale": 1.0, "sign": 1.0, "flipped_at": None})
            cur_scale, cur_sign, flipped_at = m["scale"], m["sign"], m["flipped_at"]

            # 표본이 적으면 섣불리 바꾸지 않는다.
            min_samples = max(4, window // 4)
            if total < min_samples:
                verdicts.append(f"{name}: 표본부족({total})")
                continue

            acc = hits / total
            ranked.append((acc, name))

            # 1) 부호 학습 — '현재 부호로 쌓인 증거'만 보고 결정(반전 직후 thrashing 방지).
            #    반전하면 flipped_at 을 갱신해, 새 부호가 충분히 평가되기 전엔 재반전 금지.
            new_sign = cur_sign
            new_flipped_at = flipped_at
            ph, pt = store.predictor_accuracy_since(name, flipped_at)
            if pt >= min_samples and (ph / pt) < FLIP_THRESHOLD:
                new_sign = -cur_sign
                new_flipped_at = cycle_date

            # 2) 크기 보정 — 예측/실제 변동폭 비율로 게인 조정
            new_scale = cur_scale
            pairs = store.recent_pred_actual(name, window, stage=OFFICIAL_PREDICT_POINT)
            if pairs:
                mp = mean(abs(p) for p, _ in pairs)
                ma = mean(abs(a) for _, a in pairs)
                if mp > 1e-6:
                    target = cur_scale * (ma / mp)
                    new_scale = (1 - SCALE_SMOOTH) * cur_scale + SCALE_SMOOTH * target
                    new_scale = max(SCALE_MIN, min(SCALE_MAX, new_scale))

            if abs(new_scale - cur_scale) > 0.01 or new_sign != cur_sign:
                store.set_predictor_param(name, round(new_scale, 3), new_sign,
                                          new_flipped_at)
                note = []
                if new_sign != cur_sign:
                    note.append("부호반전")
                if abs(new_scale - cur_scale) > 0.01:
                    note.append(f"스케일 {cur_scale:.2f}→{new_scale:.2f}")
                changes.append(f"{name}({acc:.2f}): " + ", ".join(note))

            # 진단 코멘트
            if new_sign != cur_sign:
                advice = "반예측적 → 신호반전 적용"
            elif acc < 0.5:
                advice = "랜덤 이하 → 스케일 보정"
            elif acc >= 0.6:
                advice = "우수 → 가중치 확대 후보"
            else:
                advice = "보통"
            verdicts.append(f"{name}: {acc:.2f} {advice}")

        headline = ""
        if ranked:
            ranked.sort(reverse=True)
            best, worst = ranked[0], ranked[-1]
            headline = (f"최고: {best[1]}({best[0]:.2f}), "
                        f"최저: {worst[1]}({worst[0]:.2f}). ")

        store.log_improver(cycle_date, self.name, "critique",
                           headline + " | ".join(verdicts))
        if changes:
            store.log_improver(cycle_date, self.name, "tune",
                               "자가보정 적용 | " + " · ".join(changes))
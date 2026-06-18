"""예측 에이전트 #5 — LLM 추론 종합.

뉴스/애널리스트/시세 신호를 LLM(Anthropic)에 넘겨 추론하게 한다.
API 키가 없거나 오프라인이면 세 신호를 가중 결합하는 휴리스틱으로 폴백한다.
"""
from __future__ import annotations

import json
from statistics import mean

from .base_predictor import BasePredictor, PredictorContext
from ...config import SETTINGS
from ...models import Prediction


class LLMReasonerPredictor(BasePredictor):
    name = "llm_reasoner"
    description = "뉴스·애널리스트·시세를 LLM으로 추론 종합 (멀티신호 추론, 폴백 포함)"

    def predict_one(self, ctx: PredictorContext) -> Prediction:
        if SETTINGS.use_llm and SETTINGS.anthropic_api_key:
            result = self._llm_predict(ctx)
            if result is not None:
                return result
        return self._heuristic(ctx)

    # ---- 폴백: 세 신호 가중 결합 ----
    def _heuristic(self, ctx: PredictorContext) -> Prediction:
        sent = mean([n.sentiment for n in ctx.news]) if ctx.news else 0.0
        if ctx.analyst_views:
            rmap = {"buy": 1.0, "hold": 0.0, "sell": -1.0}
            analyst = mean([rmap.get(v.rating, 0.0) for v in ctx.analyst_views])
        else:
            analyst = 0.0
        if len(ctx.history) >= 5:
            mom = (ctx.history[-1] - ctx.history[-5]) / ctx.history[-5] * 100.0
        else:
            mom = 0.0
        expected = round(sent * 0.6 + analyst * 0.5 + mom * 0.1, 3)
        # 세 신호가 같은 부호로 모이면 신뢰↑
        signs = [s > 0 for s in (sent, analyst, mom) if abs(s) > 1e-6]
        agree = (len(set(signs)) <= 1) and len(signs) >= 2
        confidence = 0.55 if agree else 0.4
        rationale = (f"[휴리스틱] 감성 {sent:+.2f}, 애널리스트 {analyst:+.2f}, "
                     f"모멘텀 {mom:+.2f}% 결합")
        return self._mk(ctx, expected, confidence, rationale)

    # ---- 실제 LLM 호출 ----
    def _llm_predict(self, ctx: PredictorContext) -> Prediction | None:
        try:
            from anthropic import Anthropic  # type: ignore
        except Exception:
            return None
        client = Anthropic(api_key=SETTINGS.anthropic_api_key)
        news_lines = "\n".join(f"- ({n.sentiment:+.2f}) {n.title}" for n in ctx.news[:8])
        analyst_lines = "\n".join(
            f"- {v.firm}: {v.rating} (목표 {v.target_return_pct:+.1f}%)"
            for v in ctx.analyst_views[:8]
        )
        recent = ctx.history[-7:] if ctx.history else []
        prompt = (
            f"당신은 퀀트 애널리스트입니다. 종목 {ctx.symbol}({ctx.market})의 "
            f"다음 거래일 수익률을 예측하세요.\n\n"
            f"[최근 종가] {recent}\n[뉴스]\n{news_lines}\n[애널리스트]\n{analyst_lines}\n\n"
            'JSON만 출력: {"expected_return_pct": <float>, '
            '"confidence": <0~1 float>, "rationale": "<한 줄>"}'
        )
        try:
            msg = client.messages.create(
                model=SETTINGS.llm_model, max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if hasattr(b, "text"))
            start, end = text.find("{"), text.rfind("}")
            data = json.loads(text[start:end + 1])
            return self._mk(
                ctx, float(data["expected_return_pct"]),
                float(data["confidence"]),
                "[LLM] " + str(data.get("rationale", "")),
            )
        except Exception:
            return None

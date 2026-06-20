"""LLM 토론 하네스 — 강세·약세·심판 에이전트 + 회고(reflection) 루프.

기존 5개 휴리스틱 예측기의 앙상블 결과를 '초안'으로 받아, 세 역할의 LLM
에이전트가 토론해 그 초안을 비평·교정한다.

  1) 강세(bull)  — 상승 논거를 최대한 끌어모은다.
  2) 약세(bear)  — 하락/리스크 논거를 최대한 끌어모은다.
  3) 심판(judge) — 양측 + 앙상블 초안 + 과거 회고 교훈을 종합해
                   최종 기대수익률·신뢰도·방향을 확정한다.

④ 평가 시점에는 reflect() 로 그날 가장 크게 빗나간 종목들을 돌아보고
'교훈'을 한 줄씩 만들어 DB에 쌓는다. 다음 토론의 심판 프롬프트에 주입되어
시스템이 자기 실수에서 배우게 한다(harness engineering 의 핵심).

LLM(Groq) 키가 없거나 호출이 실패하면 앙상블 초안을 그대로 통과시킨다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .llm import GroqClient, groq_available
from .models import EnsemblePrediction, NewsItem, AnalystView, to_direction

log = logging.getLogger(__name__)

# 토론이 앙상블 초안을 한 번에 얼마나 끌어당길 수 있는지 상한(±%p).
# 휴리스틱 신호를 LLM 잡음이 통째로 뒤집지 못하게 가드레일을 둔다.
_MAX_SHIFT_PCT = 3.0


@dataclass
class HarnessVerdict:
    """심판이 확정한 최종 예측 + 토론 근거."""

    expected_return_pct: float
    confidence: float
    direction: str
    bull_case: str = ""
    bear_case: str = ""
    verdict: str = ""
    used_llm: bool = False
    lessons_applied: list[str] = field(default_factory=list)


def _fmt_news(news: list[NewsItem], limit: int = 8) -> str:
    if not news:
        return "(관련 뉴스 없음)"
    return "\n".join(f"- ({n.sentiment:+.2f}) {n.title}" for n in news[:limit])


def _fmt_views(views: list[AnalystView], limit: int = 6) -> str:
    if not views:
        return "(애널리스트 의견 없음)"
    return "\n".join(
        f"- {v.firm}: {v.rating} (목표 {v.target_return_pct:+.1f}%)"
        for v in views[:limit]
    )


class DebateHarness:
    """강세·약세·심판 토론을 한 종목·한 시점에 대해 실행."""

    def __init__(self, client: GroqClient | None = None):
        self.client = client or GroqClient()

    @property
    def enabled(self) -> bool:
        return groq_available()

    # ---- 한 종목 토론 ----
    def run(self, symbol: str, name: str, market: str,
            ensemble: EnsemblePrediction, history: list[float],
            news: list[NewsItem], views: list[AnalystView],
            lessons: list[str] | None = None) -> HarnessVerdict:
        draft = HarnessVerdict(
            expected_return_pct=ensemble.expected_return_pct,
            confidence=ensemble.confidence,
            direction=ensemble.direction,
        )
        if not self.enabled:
            return draft

        recent = [round(x, 2) for x in history[-7:]] if history else []
        news_txt = _fmt_news(news)
        views_txt = _fmt_views(views)
        ctx = (
            f"종목: {name}({symbol}, {market})\n"
            f"최근 종가(7일): {recent}\n"
            f"앙상블 초안: 방향 {ensemble.direction}, "
            f"기대수익률 {ensemble.expected_return_pct:+.2f}%, "
            f"신뢰도 {ensemble.confidence:.2f}\n"
            f"[뉴스]\n{news_txt}\n[애널리스트]\n{views_txt}"
        )

        bull = self.client.chat(
            system=("너는 강세론 애널리스트다. 다음 거래일 상승 논거만 찾아 "
                    "냉정하게 정리한다. JSON 으로만 답한다."),
            user=(ctx + '\n\n상승 논거를 JSON 으로: '
                  '{"case": "<2~3문장 핵심 논거>", "upside_pct": <예상 상승폭 float>}'),
            max_tokens=400,
        )
        bear = self.client.chat(
            system=("너는 약세론·리스크 애널리스트다. 다음 거래일 하락/리스크 "
                    "논거만 찾아 냉정하게 정리한다. JSON 으로만 답한다."),
            user=(ctx + '\n\n하락 논거를 JSON 으로: '
                  '{"case": "<2~3문장 핵심 논거>", "downside_pct": <예상 하락폭 float, 음수>}'),
            max_tokens=400,
        )
        # 강세/약세 중 하나라도 실패하면 LLM 신호를 신뢰하지 않고 초안 유지
        if bull is None or bear is None:
            log.info("harness: %s 토론 일부 실패 → 앙상블 초안 유지", symbol)
            return draft

        lessons_txt = ("\n".join(f"- {x}" for x in lessons[:5])
                       if lessons else "(아직 없음)")
        judge = self.client.chat_json(
            system=("너는 수석 심판 애널리스트다. 강세·약세 논거와 앙상블 초안, "
                    "그리고 과거 회고 교훈을 종합해 다음 거래일 수익률을 최종 "
                    "확정한다. 한쪽으로 쏠리지 말고 증거의 무게로 판단하라. "
                    "JSON 으로만 답한다."),
            user=(
                f"{ctx}\n\n[강세 논거]\n{bull}\n\n[약세 논거]\n{bear}\n\n"
                f"[과거 회고 교훈]\n{lessons_txt}\n\n"
                "최종 판단을 JSON 으로: "
                '{"expected_return_pct": <float, 다음 거래일 %>, '
                '"confidence": <0~1 float, 이 예측을 얼마나 믿는가>, '
                '"verdict": "<2~3문장 최종 근거>"}'
            ),
            max_tokens=500,
        )
        if not judge or "expected_return_pct" not in judge:
            log.info("harness: %s 심판 파싱 실패 → 앙상블 초안 유지", symbol)
            return draft

        try:
            llm_ret = float(judge["expected_return_pct"])
            llm_conf = float(judge.get("confidence", ensemble.confidence))
        except (TypeError, ValueError):
            return draft

        # 가드레일: 앙상블 초안에서 ±_MAX_SHIFT_PCT 이상은 끌어당기지 못한다.
        base = ensemble.expected_return_pct
        shifted = max(base - _MAX_SHIFT_PCT, min(base + _MAX_SHIFT_PCT, llm_ret))
        conf = max(0.0, min(1.0, llm_conf))

        return HarnessVerdict(
            expected_return_pct=round(shifted, 3),
            confidence=round(conf, 3),
            direction=to_direction(shifted),
            bull_case=_extract_case(bull),
            bear_case=_extract_case(bear),
            verdict=str(judge.get("verdict", ""))[:500],
            used_llm=True,
            lessons_applied=list(lessons or [])[:5],
        )

    # ---- 회고 루프: 빗나간 예측에서 교훈 추출 ----
    def reflect(self, symbol: str, name: str,
                predicted_pct: float, actual_pct: float,
                news: list[NewsItem]) -> str | None:
        """한 종목의 예측 vs 실제 괴리를 돌아보고 한 줄 교훈을 만든다."""
        if not self.enabled:
            return None
        news_txt = _fmt_news(news, limit=6)
        out = self.client.chat_json(
            system=("너는 예측 시스템을 개선하는 회고 코치다. 예측이 왜 빗나갔는지 "
                    "한 문장으로 진단하고, 다음에 반영할 교훈 한 줄을 만든다. "
                    "JSON 으로만 답한다."),
            user=(
                f"종목: {name}({symbol})\n"
                f"예측 수익률: {predicted_pct:+.2f}%\n"
                f"실제 수익률: {actual_pct:+.2f}%\n"
                f"오차: {abs(predicted_pct - actual_pct):.2f}%p\n"
                f"[당시 뉴스]\n{news_txt}\n\n"
                "회고를 JSON 으로: "
                '{"lesson": "<다음 예측에 적용할 교훈 한 줄>"}'
            ),
            max_tokens=200,
        )
        if not out:
            return None
        lesson = str(out.get("lesson", "")).strip()
        return lesson or None


def _extract_case(raw: str) -> str:
    """강세/약세 응답 텍스트에서 case 문장만 뽑아낸다(파싱 실패 시 원문 절단)."""
    import json
    try:
        data = json.loads(raw)
        return str(data.get("case", ""))[:500]
    except Exception:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            try:
                return str(json.loads(raw[start:end + 1]).get("case", ""))[:500]
            except Exception:
                pass
        return raw.strip()[:500]

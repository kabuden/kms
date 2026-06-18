"""도메인 데이터 모델 (의존성 없는 dataclass)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NewsItem:
    market: str
    source: str
    title: str
    summary: str
    url: str
    published_at: str
    sentiment: float = 0.0   # -1.0(부정) ~ +1.0(긍정)


@dataclass
class AnalystView:
    """애널리스트 의견 1건 (등급/목표가)."""

    market: str
    firm: str
    symbol: str
    rating: str              # "buy" | "hold" | "sell"
    target_return_pct: float # 현재가 대비 목표 수익률(%)


@dataclass
class Prediction:
    """예측 에이전트 1명이 1종목에 대해 내린 예측."""

    cycle_date: str
    symbol: str
    predictor: str
    direction: str           # "up" | "down" | "flat"
    expected_return_pct: float
    confidence: float        # 0.0 ~ 1.0
    rationale: str = ""


@dataclass
class EnsemblePrediction:
    cycle_date: str
    symbol: str
    direction: str
    expected_return_pct: float
    confidence: float
    weights: dict[str, float] = field(default_factory=dict)
    contributors: dict[str, str] = field(default_factory=dict)  # predictor -> direction


@dataclass
class Actual:
    cycle_date: str
    symbol: str
    actual_return_pct: float


@dataclass
class Evaluation:
    cycle_date: str
    symbol: str
    predictor: str
    predicted_direction: str
    actual_direction: str
    hit: bool
    abs_error: float         # |예측수익률 - 실제수익률|


def to_direction(return_pct: float, flat_band: float = 0.2) -> str:
    """수익률(%)을 방향 라벨로 변환. ±flat_band 이내는 flat."""
    if return_pct > flat_band:
        return "up"
    if return_pct < -flat_band:
        return "down"
    return "flat"

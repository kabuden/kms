"""시스템 전역 설정.

환경변수로 동작을 조정한다. 외부 네트워크/LLM 키가 없어도
오프라인 데모 모드로 완전히 동작하도록 기본값을 잡았다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


def _flag(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class TickerSpec:
    """추적 대상 종목/지수 정의."""

    symbol: str          # 데이터 조회용 심볼 (예: AAPL, 005930.KS)
    name: str            # 표시 이름
    market: str          # "US" | "KR"


# ── 하루 4분석 시점 (한국장 중심) ─────────────────────────────
# 한 사이클(거래일 D)은 한국장 개장 전 분석에서 시작해 미국장 마감 후
# 평가·발전으로 끝난다. 시각은 KST 기준이며 day_offset 은 D 로부터의 일수
# (ap4 의 미국장 마감은 D+1 새벽 KST 라 1).
# role: "predict" = 예측 시점, "evaluate" = 평가·발전 시점.
KST_OFFSET_HOURS = 9


@dataclass
class AnalysisPoint:
    id: int
    key: str
    label: str
    kst_hour: int
    kst_minute: int
    day_offset: int      # 사이클 날짜 D 로부터 며칠 뒤(KST)
    role: str            # "predict" | "evaluate"
    news_scope: str      # "market" | "full"
    note: str = ""


ANALYSIS_POINTS: list[AnalysisPoint] = [
    AnalysisPoint(1, "ap1_kr_preopen", "한국장 개장 전", 8, 0, 0,
                  "predict", "market", "밤사이 미국장·해외 뉴스 반영"),
    AnalysisPoint(2, "ap2_kr_close", "한국장 마감 후", 16, 0, 0,
                  "predict", "full", "한국장 결과 + 종목 뉴스 반영"),
    AnalysisPoint(3, "ap3_us_open", "미국장 개장 후", 23, 30, 0,
                  "predict", "full", "미국장 개장 흐름 반영(공식 예측)"),
    AnalysisPoint(4, "ap4_us_close", "미국장 마감 후 (평가·발전)", 6, 30, 1,
                  "evaluate", "full", "실제 종가로 평가 + 발전 + 장기예측 정산"),
]

# 예측 시점(공식 비교용): 가장 이른 시점 vs 가장 늦은 시점
FIRST_PREDICT_POINT = "ap1_kr_preopen"   # baseline 역할
OFFICIAL_PREDICT_POINT = "ap3_us_open"   # 공식(revised) 예측


@dataclass
class Horizon:
    key: str
    label: str
    kind: str            # "bday" | "week" | "month" | "year"
    offset: int          # bday: 거래일수, month/year: 개월/년 수, week: 미사용


# 각 분석 후 내놓는 기간별 목표주가
HORIZONS: list[Horizon] = [
    Horizon("close", "다음 거래일 종가", "bday", 1),
    Horizon("week", "이번 주말", "week", 0),
    Horizon("m1", "1개월 후", "month", 1),
    Horizon("m3", "3개월 후", "month", 3),
    Horizon("m6", "6개월 후", "month", 6),
    Horizon("y1", "1년 후", "year", 1),
]


@dataclass
class Settings:
    # 데이터 소스: 네트워크가 막혀 있으면 자동으로 합성 데이터로 폴백한다.
    offline: bool = field(default_factory=lambda: _flag("SA_OFFLINE", True))
    # LLM(Anthropic) 사용 여부. 키가 없으면 휴리스틱으로 폴백.
    use_llm: bool = field(default_factory=lambda: _flag("SA_USE_LLM", False))
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY")
    )
    llm_model: str = field(
        default_factory=lambda: os.environ.get("SA_LLM_MODEL", "claude-fable-5")
    )
    # 기본은 ./data, 영구 디스크를 붙였다면 SA_DB_DIR 로 그 경로를 지정한다.
    db_path: Path = field(default_factory=lambda: Path(
        os.environ.get("SA_DB_DIR", str(DATA_DIR))) / "stock.db")

    # 실거래 신뢰도 게이트: 아래 조건을 모두 충족하면 trade_ready=True
    min_cycles_for_trust: int = field(
        default_factory=lambda: int(os.environ.get("SA_MIN_CYCLES", "10"))
    )
    min_accuracy_for_trust: float = field(
        default_factory=lambda: float(os.environ.get("SA_MIN_ACCURACY", "0.52"))
    )
    rolling_window: int = field(
        default_factory=lambda: int(os.environ.get("SA_ROLLING_WINDOW", "20"))
    )

    universe: list[TickerSpec] = field(default_factory=lambda: [
        # ── 미국 (지수 + 대형주) ──
        TickerSpec("^GSPC", "S&P 500", "US"),
        TickerSpec("^IXIC", "나스닥", "US"),
        TickerSpec("AAPL", "Apple", "US"),
        TickerSpec("MSFT", "Microsoft", "US"),
        TickerSpec("NVDA", "NVIDIA", "US"),
        TickerSpec("AMZN", "Amazon", "US"),
        TickerSpec("GOOGL", "Alphabet", "US"),
        TickerSpec("TSLA", "Tesla", "US"),
        # ── 한국 (지수 + 대형주) ──
        TickerSpec("^KS11", "코스피", "KR"),
        TickerSpec("005930.KS", "삼성전자", "KR"),
        TickerSpec("000660.KS", "SK하이닉스", "KR"),
        TickerSpec("005380.KS", "현대차", "KR"),
        TickerSpec("035420.KS", "NAVER", "KR"),
        TickerSpec("035720.KS", "카카오", "KR"),
        TickerSpec("373220.KS", "LG에너지솔루션", "KR"),
    ])

    def market_symbols(self, market: str) -> list[TickerSpec]:
        return [t for t in self.universe if t.market == market]


SETTINGS = Settings()

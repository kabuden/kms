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
    db_path: Path = field(default_factory=lambda: DATA_DIR / "stock.db")

    # 실거래 신뢰도 게이트: 아래 조건을 모두 충족하면 trade_ready=True
    min_cycles_for_trust: int = field(
        default_factory=lambda: int(os.environ.get("SA_MIN_CYCLES", "10"))
    )
    min_accuracy_for_trust: float = field(
        default_factory=lambda: float(os.environ.get("SA_MIN_ACCURACY", "0.58"))
    )
    rolling_window: int = field(
        default_factory=lambda: int(os.environ.get("SA_ROLLING_WINDOW", "20"))
    )

    universe: list[TickerSpec] = field(default_factory=lambda: [
        TickerSpec("SPY", "S&P 500 ETF", "US"),
        TickerSpec("AAPL", "Apple", "US"),
        TickerSpec("NVDA", "NVIDIA", "US"),
        TickerSpec("MSFT", "Microsoft", "US"),
        TickerSpec("^KS11", "KOSPI", "KR"),
        TickerSpec("005930.KS", "삼성전자", "KR"),
        TickerSpec("000660.KS", "SK하이닉스", "KR"),
    ])

    def market_symbols(self, market: str) -> list[TickerSpec]:
        return [t for t in self.universe if t.market == market]


SETTINGS = Settings()

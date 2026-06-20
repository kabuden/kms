"""이벤트 카탈로그 — 실적 발표·내부자 거래·CAR(누적 비정상 수익률) 계산.

공개 데이터 소스 (API 키 불필요):
  미국 실적 : Yahoo Finance v10 earningsHistory 엔드포인트
  미국 내부자거래 : SEC EDGAR Form 4 RSS + submissions.json (무료·무인증)
  한국 실적 : DART OpenAPI (SA_DART_API_KEY 환경변수 필요; 없으면 건너뜀)

CAR = 종목 일간수익률 - 벤치마크 일간수익률 의 누적합(이벤트일 기준 ±offset)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


@dataclass
class EarningsEvent:
    symbol: str
    event_date: str          # ISO "YYYY-MM-DD" (실적 발표일)
    event_type: str          # "earnings_beat" | "earnings_miss" | "earnings_inline" | "earnings_unknown"
    surprise_pct: float      # (actual-estimate)/|estimate|*100
    actual_eps: float | None
    expected_eps: float | None
    source: str              # "yfinance" | "dart"


@dataclass
class InsiderTrade:
    symbol: str
    filed_date: str          # Form 4 신고일 ISO "YYYY-MM-DD"
    transaction_date: str    # 실제 거래일 ISO "YYYY-MM-DD"
    filer: str               # 신고자 이름
    role: str                # "CEO" | "CFO" | "Director" | "Unknown"
    transaction_type: str    # "P"(매수) | "S"(매도) | "A"(부여/기타)
    shares: float
    price_per_share: float
    total_value: float
    form_type: str = "4"
    is_scheduled: bool = False  # 10b5-1 plan → 신호 약화


def categorize_surprise(surprise_pct: float | None) -> str:
    """EPS 서프라이즈율(%)로 이벤트 유형 분류."""
    if surprise_pct is None:
        return "earnings_unknown"
    if surprise_pct >= 5.0:
        return "earnings_beat"
    if surprise_pct <= -5.0:
        return "earnings_miss"
    return "earnings_inline"


def compute_car(
    symbol_series: list[tuple[str, float]],
    benchmark_series: list[tuple[str, float]],
    event_date: str,
    window_pre: int = 1,
    window_post: int = 10,
) -> dict[int, float]:
    """이벤트 전후 누적 비정상 수익률(CAR) 계산.

    symbol_series, benchmark_series : (ISO날짜, 종가) 오름차순 리스트
    event_date : 이벤트 발생일 (실적 발표일 또는 내부자 신고일)
    window_pre  : 이벤트 전 관찰 일수 (음수 offset 에 해당)
    window_post : 이벤트 후 관찰 일수 (양수 offset 에 해당)

    반환 : {day_offset : CAR%}
      day_offset 0 = 이벤트 당일, -1 = 전일, +5 = 이후 5번째 거래일
    """
    sym_map = {d: c for d, c in symbol_series}
    bench_map = {d: c for d, c in benchmark_series}
    all_dates = sorted(sym_map)

    # 이벤트일 인덱스 (없으면 가장 가까운 이후 거래일)
    event_idx: int | None = None
    for i, d in enumerate(all_dates):
        if d >= event_date:
            event_idx = i
            break
    if event_idx is None:
        return {}

    start_i = max(0, event_idx - window_pre)
    end_i = min(len(all_dates) - 1, event_idx + window_post)

    car: dict[int, float] = {}
    cumulative_ar = 0.0

    for i in range(start_i, end_i + 1):
        if i == 0:
            continue
        day = all_dates[i]
        prev_day = all_dates[i - 1]
        s0, s1 = sym_map.get(prev_day), sym_map.get(day)
        b0, b1 = bench_map.get(prev_day), bench_map.get(day)
        if not all([s0, s1, b0, b1]):
            continue
        sym_ret = (s1 - s0) / s0 * 100.0
        bench_ret = (b1 - b0) / b0 * 100.0
        cumulative_ar += sym_ret - bench_ret
        day_offset = i - event_idx
        car[day_offset] = round(cumulative_ar, 4)

    return car


def aggregate_car_records(records: list[dict]) -> dict[tuple[str, str], dict]:
    """CAR 레코드 배열에서 (event_type, sector) 별 패턴 집계.

    records : [{"event_type":…, "sector":…, "surprise_pct":…,
                "car_d1":…, "car_d5":…, "car_d10":…}, …]
    반환   : {(event_type, sector): {avg_car_d1, avg_car_d5, avg_car_d10, hit_rate, n}}
    """
    from collections import defaultdict

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        key = (r.get("event_type", "unknown"), r.get("sector", "unknown"))
        groups[key].append(r)

    patterns: dict[tuple[str, str], dict] = {}
    for (etype, sector), recs in groups.items():
        d1s = [r["car_d1"] for r in recs if r.get("car_d1") is not None]
        d5s = [r["car_d5"] for r in recs if r.get("car_d5") is not None]
        d10s = [r["car_d10"] for r in recs if r.get("car_d10") is not None]

        direction_hits = [
            1 for r in recs
            if r.get("car_d5") is not None and r.get("surprise_pct") is not None
            and ((r["surprise_pct"] > 0 and r["car_d5"] > 0) or
                 (r["surprise_pct"] < 0 and r["car_d5"] < 0))
        ]
        n = len(recs)
        patterns[(etype, sector)] = {
            "avg_car_d1": round(mean(d1s), 4) if d1s else 0.0,
            "avg_car_d5": round(mean(d5s), 4) if d5s else 0.0,
            "avg_car_d10": round(mean(d10s), 4) if d10s else 0.0,
            "hit_rate": round(len(direction_hits) / n, 3) if n else 0.5,
            "sample_count": n,
        }
    return patterns

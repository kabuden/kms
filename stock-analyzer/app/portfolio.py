"""투자 제안 엔진 — 앙상블 예측을 포트폴리오 배분으로 변환.

알고리즘:
  점수 = max(0, (신뢰도 - 임계치) × 기대수익률)
  → 신뢰도 45% 미만 또는 기대수익이 0 이하이면 제외
  → 비중 = 점수/총점수, 종목당 최대 30% 캡 후 정규화
  → 미국/한국 시장별로 분리해 각각 100% 기준 배분
  → 회피 후보: direction='down' + 신뢰도 높은 종목

trade_ready 여부에 관계없이 계산하되, 충분한 사이클 미달이면
'참고 전용' 표시를 반환한다. 최종 투자 판단은 사용자 책임이다.
"""
from __future__ import annotations

from .config import OFFICIAL_PREDICT_POINT, SETTINGS
from .storage import Storage

_CONF_FLOOR = 0.45   # 이 이하 신뢰도는 노이즈로 간주
_MAX_WEIGHT = 0.30   # 종목당 최대 비중 30%
_MIN_CYCLES = 5      # 제안 표시에 필요한 최소 사이클


def _allocate(candidates: list[dict]) -> list[dict]:
    """점수 비례 비중 배분. 종목당 최대 30%, 총합 100% 정규화."""
    items = [c.copy() for c in candidates if c.get("score", 0) > 0]
    if not items:
        return []
    total = sum(c["score"] for c in items)
    if total <= 0:
        return []
    raw = {c["symbol"]: min(_MAX_WEIGHT, c["score"] / total) for c in items}
    cap_sum = sum(raw.values())
    for c in items:
        # 정규화: 캡 적용 후 합계가 1이 되도록 스케일
        c["weight_pct"] = round(raw[c["symbol"]] / cap_sum * 100, 1)
    return sorted(items, key=lambda x: -x["weight_pct"])


def suggest(store: Storage, cycle_date: str | None = None) -> dict:
    """최신(또는 지정) 사이클의 투자 제안을 반환한다."""
    n_cycles = len(store.cycle_dates())
    conf_data = store.latest_confidence() or {}
    trade_ready = bool(conf_data.get("trade_ready"))
    rolling_acc = conf_data.get("rolling_accuracy") or 0.0

    if not cycle_date:
        dates = store.cycle_dates()
        cycle_date = dates[-1] if dates else None

    if not cycle_date or n_cycles < _MIN_CYCLES:
        return {
            "ready": False,
            "cycle_date": cycle_date,
            "n_cycles": n_cycles,
            "trade_ready": trade_ready,
            "rolling_accuracy": 0.0,
            "us_buy": [], "kr_buy": [], "avoid": [],
            "note": f"데이터 부족 — 최소 {_MIN_CYCLES}사이클 필요 (현재 {n_cycles})",
        }

    rows = store.ensemble_for_cycle(cycle_date, OFFICIAL_PREDICT_POINT)
    spec_by_symbol = {s.symbol: s for s in SETTINGS.universe}

    buy_pool: list[dict] = []
    avoid_pool: list[dict] = []

    for e in rows:
        sym = e["symbol"]
        spec = spec_by_symbol.get(sym)
        direction = e["direction"]
        conf = e["confidence"]
        ret = e["expected_return_pct"]

        base = {
            "symbol": sym,
            "name": spec.name if spec else sym,
            "market": spec.market if spec else "",
            "owned": spec.owned if spec else False,
            "direction": direction,
            "expected_return_pct": ret,
            "confidence": round(conf, 3),
            "base_price": e.get("base_price") or 0.0,
        }

        if direction == "up":
            score = (conf - _CONF_FLOOR) * ret if conf >= _CONF_FLOOR and ret > 0 else 0.0
            base["score"] = round(score, 4)
            buy_pool.append(base)
        elif direction == "down" and conf >= _CONF_FLOOR:
            base["score"] = round((conf - _CONF_FLOOR) * abs(ret), 4)
            avoid_pool.append(base)

    us_buys = _allocate([c for c in buy_pool if c["market"] == "US"])
    kr_buys = _allocate([c for c in buy_pool if c["market"] == "KR"])
    avoid_pool.sort(key=lambda x: -x.get("score", 0))

    # score 필드는 내부용이라 제거
    for c in us_buys + kr_buys + avoid_pool:
        c.pop("score", None)

    if trade_ready:
        note = (f"실거래 검증 완료 (롤링정확도 {rolling_acc:.0%}) — 투자 참고 가능 "
                f"· 반드시 분산투자 원칙 준수 · 투자 책임은 본인에게 있음")
    else:
        note = (f"학습 단계 ({n_cycles}사이클, 롤링정확도 {rolling_acc:.0%}) — "
                f"아직 참고 전용. 실거래에 사용하지 마세요.")

    return {
        "ready": True,
        "cycle_date": cycle_date,
        "n_cycles": n_cycles,
        "trade_ready": trade_ready,
        "rolling_accuracy": round(rolling_acc, 3),
        "us_buy": us_buys[:6],
        "kr_buy": kr_buys[:6],
        "avoid": avoid_pool[:4],
        "note": note,
    }

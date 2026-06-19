"""일일 리포트 생성 (표준 라이브러리만 사용).

한 사이클(거래일 D)이 ④ 평가까지 끝나면, 그날의 흐름을 사람이 읽기 좋은
마크다운으로 정리한다.

  - 신뢰도/정확도 요약
  - 시점별(① 한국개장전 → ③ 미국개장후) 예측이 어떻게 바뀌었는지
  - 뉴스 요약(시장별 건수·평균감성·주요 헤드라인)
  - 종목별 공식 예측 + 다음 거래일 실제 + 적중
  - 기간별 목표주가 하이라이트(가장 강한 상승/하락 전망)
  - 이번에 만기 도래한 장기 예측 정산 결과
  - 발전 에이전트 로그

리포트는 DB(daily_reports)에 저장되고, 데이터 디렉터리의 reports/ 폴더에도
마크다운 파일로 남긴다.
"""
from __future__ import annotations

from datetime import datetime

from .config import (
    FIRST_PREDICT_POINT,
    HORIZONS,
    OFFICIAL_PREDICT_POINT,
    SETTINGS,
)
from .storage import Storage

_WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
_DIR_KO = {"up": "▲상승", "down": "▼하락", "flat": "●보합"}
_MARKET_KO = {"US": "🇺🇸 미국", "KR": "🇰🇷 한국"}


def _fmt_price(p) -> str:
    if p is None:
        return "–"
    return f"{round(p):,}" if p >= 1000 else f"{p:,}"


def _fmt_pct(v) -> str:
    if v is None:
        return "–"
    return f"{'+' if v > 0 else ''}{v}%"


def _news_digest(store: Storage, cycle_date: str) -> dict:
    digest: dict[str, dict] = {}
    for item in store.news_for_cycle(cycle_date):
        d = digest.setdefault(item.market, {"items": [], "sum": 0.0})
        d["items"].append(item)
        d["sum"] += item.sentiment
    out = {}
    for market, d in digest.items():
        n = len(d["items"])
        out[market] = {
            "count": n,
            "avg_sentiment": round(d["sum"] / n, 3) if n else 0.0,
            "headlines": d["items"][:5],
        }
    return out


def build_report(store: Storage, cycle_date: str) -> dict:
    """리포트 마크다운 + 요약 dict 를 만든다(저장은 하지 않음)."""
    spec_by_symbol = {s.symbol: s for s in SETTINGS.universe}
    d = datetime.fromisoformat(cycle_date).date()
    weekday = _WEEKDAY_KO[d.weekday()]

    official = {e["symbol"]: e
                for e in store.ensemble_for_cycle(cycle_date, OFFICIAL_PREDICT_POINT)}
    first = {e["symbol"]: e
             for e in store.ensemble_for_cycle(cycle_date, FIRST_PREDICT_POINT)}
    conf = store.confidence_for_cycle(cycle_date) or {}
    news = _news_digest(store, cycle_date)
    horizons = store.horizons_for_cycle(cycle_date, "ensemble")
    logs = store.improver_logs_for_cycle(cycle_date)

    lines: list[str] = []
    lines.append(f"# 📊 일일 리포트 — {cycle_date} ({weekday})")
    lines.append("")

    # ── 신뢰도 ──
    lines.append("## 🎯 신뢰도 / 정확도")
    if conf:
        lines.append(f"- 학습 사이클: **{len(store.cycle_dates())}**")
        lines.append(f"- 전체 정확도: **{conf.get('overall_accuracy', 0):.2f}** · "
                     f"롤링 정확도: **{conf.get('rolling_accuracy', 0):.2f}** · "
                     f"보정 신뢰도: **{conf.get('calibrated_confidence', 0):.2f}**")
        ready = "✅ 가능" if conf.get("trade_ready") else "🧪 학습/검증 단계"
        lines.append(f"- 실거래 판정: **{ready}**")
        if conf.get("detail"):
            lines.append(f"- {conf['detail']}")
    else:
        lines.append("- 아직 평가 데이터가 없습니다(예측만 완료).")
    lines.append("")

    # ── 시점별 예측 변화 ──
    lines.append("## 🔄 예측 변화 (① 한국개장전 → ③ 미국개장후)")
    changed, up, down, flat = 0, 0, 0, 0
    deltas = []
    for sym, e in official.items():
        if e["direction"] == "up":
            up += 1
        elif e["direction"] == "down":
            down += 1
        else:
            flat += 1
        b = first.get(sym)
        if b:
            deltas.append(e["expected_return_pct"] - b["expected_return_pct"])
            if b["direction"] != e["direction"]:
                changed += 1
    avg_delta = round(sum(deltas) / len(deltas), 3) if deltas else 0.0
    lines.append(f"- 공식 예측 분포: 상승 {up} · 하락 {down} · 보합 {flat}")
    lines.append(f"- 방향 전환 종목: **{changed}**개 · 평균 기대수익률 변화: "
                 f"**{_fmt_pct(avg_delta)}p**")
    lines.append("")

    # ── 뉴스 요약 ──
    lines.append("## 📰 뉴스 요약")
    if news:
        for market, info in news.items():
            tone = ("긍정" if info["avg_sentiment"] > 0.05
                    else "부정" if info["avg_sentiment"] < -0.05 else "중립")
            lines.append(f"### {_MARKET_KO.get(market, market)} — "
                         f"{info['count']}건 · 평균감성 {info['avg_sentiment']} ({tone})")
            for h in info["headlines"]:
                lines.append(f"- {h.title} _({h.source})_")
    else:
        lines.append("- 수집된 뉴스가 없습니다.")
    lines.append("")

    # ── 종목별 공식 예측 + 실제 ──
    lines.append("## 📈 종목별 공식 예측 (③ 미국개장후) · 다음 거래일 실제")
    hits = total = 0
    close_target = {}
    for h in horizons:
        if h["horizon"] == "close" and h["analysis_point"] == 3:
            close_target[h["symbol"]] = h["target_price"]
    for sym, e in official.items():
        spec = spec_by_symbol.get(sym)
        name = spec.name if spec else sym
        actual = store.actual(cycle_date, sym)
        tgt = close_target.get(sym)
        line = (f"- **{name}**: {_DIR_KO.get(e['direction'])} "
                f"{_fmt_pct(e['expected_return_pct'])} (신뢰 "
                f"{round(e['confidence'] * 100)}%)")
        if tgt is not None:
            line += f" · 다음종가 목표 {_fmt_price(tgt)}"
        if actual is not None:
            total += 1
            hit = _dir(actual) == e["direction"]
            hits += int(hit)
            line += f" · 실제 {_fmt_pct(round(actual, 2))} {'✅' if hit else '❌'}"
        else:
            line += " · 실제 미정"
        lines.append(line)
    if total:
        lines.append("")
        lines.append(f"> 다음 거래일 방향 적중: **{hits}/{total}** "
                     f"({round(hits / total * 100)}%)")
    lines.append("")

    # ── 기간별 목표주가 하이라이트 ──
    lines.append("## 🗓️ 기간별 목표주가 하이라이트 (1년 전망 기준, 공식 시점)")
    y1 = [h for h in horizons
          if h["horizon"] == "y1" and h["analysis_point"] == 3]
    if y1:
        y1.sort(key=lambda x: x["expected_return_pct"], reverse=True)
        top = y1[0]
        bot = y1[-1]
        tn = spec_by_symbol.get(top["symbol"])
        bn = spec_by_symbol.get(bot["symbol"])
        lines.append(f"- 최대 상승 전망: **{tn.name if tn else top['symbol']}** "
                     f"{_fmt_pct(top['expected_return_pct'])} → 목표 "
                     f"{_fmt_price(top['target_price'])}")
        lines.append(f"- 최대 하락 전망: **{bn.name if bn else bot['symbol']}** "
                     f"{_fmt_pct(bot['expected_return_pct'])} → 목표 "
                     f"{_fmt_price(bot['target_price'])}")
    else:
        lines.append("- 장기 전망 데이터가 아직 없습니다.")
    lines.append("")

    # ── 장기 예측 정산 ──
    settled = [h for h in horizons if h.get("actual_price") is not None]
    if settled:
        s_hits = sum(1 for h in settled if h.get("hit") == 1)
        lines.append("## ✅ 장기 예측 정산 (만기 도래분)")
        lines.append(f"- 이번 사이클에 정산된 기간 예측: **{len(settled)}**건 · "
                     f"방향 적중 {s_hits}건")
        lines.append("")

    # ── 발전 로그 ──
    lines.append("## 🔧 발전 에이전트 로그")
    if logs:
        for l in logs:
            lines.append(f"- **{l['improver']}** · {l['action']}: {l['detail']}")
    else:
        lines.append("- 이번 사이클 발전 로그가 없습니다.")
    lines.append("")
    lines.append("---")
    lines.append("> ⚠️ 연구·학습용 리포트입니다. 투자 판단의 유일한 근거로 쓰지 마세요.")

    markdown = "\n".join(lines)
    summary = {
        "cycle_date": cycle_date,
        "weekday": weekday,
        "symbols": len(official),
        "dist": {"up": up, "down": down, "flat": flat},
        "direction_changes": changed,
        "avg_delta_pct": avg_delta,
        "next_close_hits": hits,
        "next_close_total": total,
        "rolling_accuracy": conf.get("rolling_accuracy"),
        "calibrated_confidence": conf.get("calibrated_confidence"),
        "trade_ready": bool(conf.get("trade_ready")),
        "settled_horizons": len(settled),
    }
    return {"cycle_date": cycle_date, "markdown": markdown, "summary": summary}


def _dir(return_pct: float, band: float = 0.2) -> str:
    if return_pct > band:
        return "up"
    if return_pct < -band:
        return "down"
    return "flat"


def generate_and_store(store: Storage, cycle_date: str) -> dict:
    """리포트를 생성해 DB 저장 + 파일(reports/<date>.md)로 남긴다."""
    report = build_report(store, cycle_date)
    store.save_report(cycle_date, report["markdown"], report["summary"])
    try:
        reports_dir = SETTINGS.db_path.parent / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / f"{cycle_date}.md").write_text(
            report["markdown"], encoding="utf-8")
    except Exception:
        pass  # 파일 쓰기 실패는 치명적이지 않음(DB에 이미 저장됨)
    return report

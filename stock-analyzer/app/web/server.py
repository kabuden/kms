"""웹 대시보드 서버 (표준 라이브러리만 사용 → 어디서나 실행 가능).

JSON API + 정적 파일을 함께 제공한다. FastAPI 등 외부 의존성이 필요 없다.

엔드포인트:
  GET /api/overview        최신 신뢰도/정확도/실거래 가능 여부
  GET /api/agents          에이전트 명단(수집2·예측5·발전3)
  GET /api/latest          최신 사이클의 앙상블 예측
  GET /api/cycle?date=...  특정 사이클 상세(개별 예측 포함)
  GET /api/history         정확도/신뢰도 추이
  GET /api/predictors      예측 에이전트별 적중률
  GET /api/improver-logs   발전 에이전트 로그
  GET /api/schedule        오늘 스케줄 현황 + 최근 실행 로그
  GET /api/reports         일일 리포트 목록(요약)
  GET /api/report?date=... 특정/최신 일일 리포트(마크다운 본문)
  POST /api/run-cycle      새 사이클 실행(예측+평가+발전)
  POST /api/run-slot       특정 분석 시점 즉시 실행 {"point": 1~4, "date": "..."}
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..config import (
    ANALYSIS_POINTS,
    FIRST_PREDICT_POINT,
    HORIZONS,
    OFFICIAL_PREDICT_POINT,
    SETTINGS,
)
from ..evaluation import magnitude_accuracy
from ..orchestrator import Orchestrator
from ..portfolio import suggest as portfolio_suggest
from ..scheduler import schedule_status
from ..storage import Storage

PREDICT_POINTS = [p for p in ANALYSIS_POINTS if p.role == "predict"]

STATIC_DIR = Path(__file__).resolve().parent / "static"
ENSEMBLE_KEY = "__ensemble__"
ENSEMBLE_BASELINE_KEY = "__ensemble_baseline__"


def _build_overview(store: Storage) -> dict:
    conf = store.latest_confidence() or {}
    roster_predictors = []
    for name in ["momentum", "sentiment", "analyst_consensus",
                 "mean_reversion", "llm_reasoner"]:
        hits, total = store.predictor_accuracy(name)
        roster_predictors.append({
            "predictor": name, "hits": hits, "total": total,
            "accuracy": round(hits / total, 3) if total else None,
        })
    e_hits, e_total = store.predictor_accuracy(ENSEMBLE_KEY)
    b_hits, b_total = store.predictor_accuracy(ENSEMBLE_BASELINE_KEY)
    return {
        "offline": SETTINGS.offline,
        "use_llm": SETTINGS.use_llm,
        "cycles": len(store.cycle_dates()),
        "min_cycles_for_trust": SETTINGS.min_cycles_for_trust,
        "min_accuracy_for_trust": SETTINGS.min_accuracy_for_trust,
        "ensemble_accuracy": round(e_hits / e_total, 3) if e_total else None,
        "ensemble_samples": e_total,
        # 뉴스 반영 효과: 수정 예측 정확도 vs 1차 예측 정확도
        "baseline_accuracy": round(b_hits / b_total, 3) if b_total else None,
        "news_value": round((e_hits / e_total) - (b_hits / b_total), 3)
        if e_total and b_total else None,
        "confidence": conf,
        "predictors": roster_predictors,
    }


class Handler(BaseHTTPRequestHandler):
    # ThreadingHTTPServer 는 요청마다 스레드를 만든다. SQLite 연결은
    # 스레드 간 공유가 안 되므로 요청마다 새 연결/오케스트레이터를 연다
    # (파일 DB라 비용이 작고 완전히 스레드 안전하다).
    def _open(self) -> tuple[Storage, Orchestrator]:
        store = Storage(SETTINGS.db_path)
        return store, Orchestrator(store)

    def log_message(self, *args):  # 콘솔 소음 억제
        pass

    def _json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str):
        if path == "/" or path == "":
            path = "/index.html"
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if not str(target).startswith(str(STATIC_DIR)) or not target.is_file():
            self._json({"error": "not found"}, 404)
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
        }.get(target.suffix, "application/octet-stream")
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if not path.startswith("/api/"):
            self._serve_static(path)
            return
        store = None
        try:
            store, orch = self._open()
            if path == "/api/overview":
                self._json(_build_overview(store))
            elif path == "/api/agents":
                self._json(orch.agent_roster())
            elif path == "/api/latest":
                dates = store.cycle_dates()
                if not dates:
                    self._json({"cycle_date": None, "rows": []})
                    return
                self._json(self._cycle_detail(store, dates[-1]))
            elif path == "/api/cycle":
                d = (qs.get("date") or [None])[0]
                if not d:
                    self._json({"error": "date required"}, 400)
                    return
                self._json(self._cycle_detail(store, d))
            elif path == "/api/history":
                self._json({"history": store.accuracy_history()})
            elif path == "/api/predictors":
                self._json(_build_overview(store)["predictors"])
            elif path == "/api/improver-logs":
                self._json({"logs": store.recent_improver_logs(60)})
            elif path == "/api/cycles":
                self._json({"cycles": store.cycle_dates()})
            elif path == "/api/schedule":
                self._json(schedule_status(store))
            elif path == "/api/reports":
                self._json({"reports": store.report_list()})
            elif path == "/api/report":
                d = (qs.get("date") or [None])[0]
                rep = store.get_report(d) if d else (
                    store.report_list()[:1] or [None])[0]
                if rep and not d:  # 최신 리포트 본문까지 채워서 반환
                    rep = store.get_report(rep["cycle_date"])
                if not rep:
                    self._json({"error": "report not found"}, 404)
                    return
                self._json(rep)
            elif path == "/api/portfolio":
                d = (qs.get("date") or [None])[0]
                self._json(portfolio_suggest(store, d))
            elif path == "/api/discoveries":
                self._json({"discoveries": store.get_discoveries()})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:  # 견고성: 500 대신 메시지 반환
            self._json({"error": str(exc)}, 500)
        finally:
            if store:
                store.close()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path not in ("/api/run-cycle", "/api/run-slot", "/api/discoveries/dismiss"):
            self._json({"error": "not found"}, 404)
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except Exception:
            payload = {}
        store = None
        try:
            store, orch = self._open()
            if path == "/api/discoveries/dismiss":
                sym = payload.get("symbol", "")
                if not sym:
                    self._json({"error": "symbol required"}, 400)
                    return
                store.dismiss_discovery(sym)
                self._json({"ok": True})
            elif path == "/api/run-cycle":
                cycle_date = payload.get("date") or self._next_date(store)
                result = orch.run_full_cycle(cycle_date)
                self._json({"ok": True, "result": result})
            else:  # /api/run-slot  (분석 시점 1~4 즉시 실행)
                point_id = int(payload.get("slot") or payload.get("point") or 0)
                cycle_date = payload.get("date") or date.today().isoformat()
                if point_id not in (1, 2, 3, 4):
                    self._json({"error": "point must be 1, 2, 3, or 4"}, 400)
                    return
                result = orch.run_analysis_point(cycle_date, point_id)
                store.log_scheduler(cycle_date, point_id, "manual", "수동 실행")
                self._json({"ok": True, "point": point_id,
                            "cycle_date": cycle_date, "result": result})
        except Exception as exc:
            self._json({"error": str(exc)}, 500)
        finally:
            if store:
                store.close()

    def _next_date(self, store: Storage) -> str:
        dates = store.cycle_dates()
        if not dates:
            return date.today().isoformat()
        last = datetime.fromisoformat(dates[-1]).date()
        return (last + timedelta(days=1)).isoformat()

    def _news_digest(self, store: Storage, cycle_date: str) -> dict:
        digest = {}
        for item in store.news_for_cycle(cycle_date):
            d = digest.setdefault(item.market, {"items": [], "sum": 0.0})
            d["items"].append({"title": item.title, "sentiment": item.sentiment,
                               "source": item.source})
            d["sum"] += item.sentiment
        out = {}
        for market, d in digest.items():
            n = len(d["items"])
            out[market] = {
                "count": n,
                "avg_sentiment": round(d["sum"] / n, 3) if n else 0.0,
                "headlines": d["items"][:6],
            }
        return out

    def _cycle_detail(self, store: Storage, cycle_date: str) -> dict:
        spec_by_symbol = {s.symbol: s for s in SETTINGS.universe}

        # 시점별 앙상블 + 개별 예측 수집
        point_ensembles: dict[str, dict[str, dict]] = {}   # key -> symbol -> ens
        point_preds: dict[str, dict[str, list]] = {}       # key -> symbol -> preds
        for pt in PREDICT_POINTS:
            point_ensembles[pt.key] = {
                e["symbol"]: e for e in store.ensemble_for_cycle(cycle_date, pt.key)}
            pp: dict[str, list] = {}
            for p in store.predictions_for_cycle(cycle_date, pt.key):
                pp.setdefault(p.symbol, []).append({
                    "predictor": p.predictor, "direction": p.direction,
                    "expected_return_pct": p.expected_return_pct,
                    "confidence": p.confidence, "rationale": p.rationale,
                })
            point_preds[pt.key] = pp

        # 기간별 목표주가 (시점별로 묶기). 라벨은 설정에서 주입.
        horizon_label = {h.key: h.label for h in HORIZONS}
        horizons_by_symbol: dict[str, dict[int, list]] = {}
        for h in store.horizons_for_cycle(cycle_date, "ensemble"):
            h["label"] = horizon_label.get(h["horizon"], h["horizon"])
            horizons_by_symbol.setdefault(h["symbol"], {}) \
                .setdefault(h["analysis_point"], []).append(h)

        # 정렬: HORIZONS 정의 순서대로
        horizon_order = {h.key: i for i, h in enumerate(HORIZONS)}
        for sym, by_pt in horizons_by_symbol.items():
            for ap, lst in by_pt.items():
                lst.sort(key=lambda x: horizon_order.get(x["horizon"], 99))

        official_key = OFFICIAL_PREDICT_POINT
        first_key = FIRST_PREDICT_POINT
        official_id = next(p.id for p in PREDICT_POINTS if p.key == official_key)

        rows = []
        # 공식 시점에 예측된 종목 기준으로 행 구성
        symbols = list(point_ensembles.get(official_key, {}).keys()) \
            or list(spec_by_symbol.keys())
        for sym in symbols:
            spec = spec_by_symbol.get(sym)
            official = point_ensembles.get(official_key, {}).get(sym)
            first = point_ensembles.get(first_key, {}).get(sym)
            if not official:
                continue
            delta = round(official["expected_return_pct"]
                          - first["expected_return_pct"], 3) if first else None
            points = []
            for pt in PREDICT_POINTS:
                e = point_ensembles.get(pt.key, {}).get(sym)
                if not e:
                    continue
                points.append({
                    "point": pt.id, "key": pt.key, "label": pt.label,
                    "note": pt.note,
                    "direction": e["direction"],
                    "expected_return_pct": e["expected_return_pct"],
                    "confidence": e["confidence"],
                    "base_price": e.get("base_price"),
                    "predictors": point_preds.get(pt.key, {}).get(sym, []),
                })
            actual_ret = store.actual(cycle_date, sym)
            rows.append({
                "symbol": sym,
                "name": spec.name if spec else sym,
                "market": spec.market if spec else "",
                "sector": spec.sector if spec else "",
                "owned": spec.owned if spec else False,
                "base_price": official.get("base_price"),
                "first": first,                  # 한국개장전(최초) 예측
                "ensemble": official,            # 미국개장후(공식) 예측
                "delta_pct": delta,              # 최초 → 공식 기대수익률 변화
                "direction_changed": (first is not None
                                      and first["direction"] != official["direction"]),
                "actual_return_pct": actual_ret,
                # 크기 고려 정확도 지수: |예측−실제| 절대값이 같아도
                # 큰 변동을 맞힌 예측을 더 높게 평가(상대오차 기반)
                "accuracy_score": (
                    magnitude_accuracy(official["expected_return_pct"], actual_ret)
                    if actual_ret is not None else None),
                "points": points,                # 시점별 예측 변화
                # 공식 시점 기준 기간별 목표주가(있으면)
                "horizons": horizons_by_symbol.get(sym, {}).get(official_id, []),
            })
        return {"cycle_date": cycle_date, "rows": rows,
                "points_meta": [{"id": p.id, "key": p.key, "label": p.label,
                                 "note": p.note} for p in PREDICT_POINTS],
                "news": self._news_digest(store, cycle_date)}


def _seed_if_empty(store: Storage) -> None:
    """콜드 스타트 시 대시보드가 비어 보이지 않도록 합성 백테스트로 시드한다.

    SA_SEED_CYCLES > 0 이고 아직 사이클이 없을 때만 동작한다. 무료 호스팅은
    디스크가 비휘발성이 아니라 재시작마다 DB가 초기화되므로, 이 옵션으로
    첫 화면에 학습 곡선을 채워 둘 수 있다(모두 오프라인 합성 데이터).
    """
    import os
    from datetime import date, timedelta

    n = int(os.environ.get("SA_SEED_CYCLES", "0") or "0")
    if n <= 0 or store.cycle_dates():
        return
    orch = Orchestrator(store)
    start = date.today() - timedelta(days=n)
    for i in range(n):
        orch.run_full_cycle((start + timedelta(days=i)).isoformat())
    mode = "실시세" if not SETTINGS.offline else "합성"
    print(f"🌱 시드 완료: {n} 사이클({mode})")


def _restore_if_available() -> None:
    """콜드 스타트(로컬 DB 없음) 시 GitHub 스냅샷에서 학습 DB를 복원한다.

    Render 무료 티어는 디스크가 휘발성이라 재시작마다 DB가 사라진다.
    SA_GITHUB_TOKEN 이 설정돼 있고 데이터 브랜치에 스냅샷이 있으면, 그동안
    쌓은 학습(예측·실제·평가·가중치·신뢰도)을 그대로 이어받는다.
    """
    if SETTINGS.db_path.exists():
        return  # 이미 로컬 DB 가 있으면(웜 스타트) 복원하지 않는다
    try:
        from ..github_sync import restore_db_snapshot
        if restore_db_snapshot(SETTINGS.db_path):
            print("☁️  GitHub 스냅샷에서 학습 DB 복원 완료")
    except Exception as exc:  # 복원 실패는 치명적이지 않음(빈 DB로 시작)
        print(f"⚠️  DB 복원 건너뜀: {exc}")


def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    # 콜드 스타트면 영구 백업에서 먼저 복원(없으면 빈 DB로 진행)
    _restore_if_available()
    # DB 스키마 초기화(연결은 요청마다 새로 연다)
    store = Storage(SETTINGS.db_path)
    _seed_if_empty(store)
    store.close()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"📈 Stock Analyzer 대시보드: http://{host}:{port}  "
          f"(offline={SETTINGS.offline}, llm={SETTINGS.use_llm})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다.")

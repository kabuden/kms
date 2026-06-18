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
  POST /api/run-cycle      새 사이클 실행(예측+평가+발전)
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ..config import SETTINGS
from ..orchestrator import Orchestrator
from ..storage import Storage

STATIC_DIR = Path(__file__).resolve().parent / "static"
ENSEMBLE_KEY = "__ensemble__"


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
    return {
        "offline": SETTINGS.offline,
        "use_llm": SETTINGS.use_llm,
        "cycles": len(store.cycle_dates()),
        "min_cycles_for_trust": SETTINGS.min_cycles_for_trust,
        "min_accuracy_for_trust": SETTINGS.min_accuracy_for_trust,
        "ensemble_accuracy": round(e_hits / e_total, 3) if e_total else None,
        "ensemble_samples": e_total,
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
            else:
                self._json({"error": "not found"}, 404)
        except Exception as exc:  # 견고성: 500 대신 메시지 반환
            self._json({"error": str(exc)}, 500)
        finally:
            if store:
                store.close()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/api/run-cycle":
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
            cycle_date = payload.get("date") or self._next_date(store)
            result = orch.run_full_cycle(cycle_date)
            self._json({"ok": True, "result": result})
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

    def _cycle_detail(self, store: Storage, cycle_date: str) -> dict:
        ensembles = store.ensemble_for_cycle(cycle_date)
        preds = store.predictions_for_cycle(cycle_date)
        by_symbol: dict[str, list] = {}
        for p in preds:
            by_symbol.setdefault(p.symbol, []).append({
                "predictor": p.predictor, "direction": p.direction,
                "expected_return_pct": p.expected_return_pct,
                "confidence": p.confidence, "rationale": p.rationale,
            })
        rows = []
        spec_by_symbol = {s.symbol: s for s in SETTINGS.universe}
        for e in ensembles:
            sym = e["symbol"]
            spec = spec_by_symbol.get(sym)
            rows.append({
                "symbol": sym,
                "name": spec.name if spec else sym,
                "market": spec.market if spec else "",
                "ensemble": e,
                "actual_return_pct": store.actual(cycle_date, sym),
                "predictors": by_symbol.get(sym, []),
            })
        return {"cycle_date": cycle_date, "rows": rows}


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
    print(f"🌱 시드 완료: {n} 사이클(합성)")


def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
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

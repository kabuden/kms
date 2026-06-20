"""SQLite 영속 계층.

예측, 실제값, 평가, 가중치, 발전 로그, 신뢰도 이력을 저장한다.
외부 의존성 없이 표준 라이브러리 sqlite3 만 사용.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    Actual,
    AnalystView,
    EnsemblePrediction,
    Evaluation,
    NewsItem,
    Prediction,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduler_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, slot INTEGER, status TEXT, detail TEXT, ran_at TEXT
);
CREATE TABLE IF NOT EXISTS daily_reports (
    cycle_date TEXT PRIMARY KEY, markdown TEXT, summary TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, market TEXT, source TEXT, title TEXT,
    summary TEXT, url TEXT, published_at TEXT, sentiment REAL,
    symbol TEXT DEFAULT '', collected_at TEXT
);
CREATE TABLE IF NOT EXISTS analyst_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, market TEXT, firm TEXT, symbol TEXT,
    rating TEXT, target_return_pct REAL
);
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, symbol TEXT, predictor TEXT, direction TEXT,
    expected_return_pct REAL, confidence REAL, rationale TEXT,
    stage TEXT DEFAULT 'revised',
    analysis_point INTEGER DEFAULT 0, base_price REAL,
    UNIQUE(cycle_date, symbol, predictor, stage)
);
CREATE TABLE IF NOT EXISTS ensemble_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, symbol TEXT, direction TEXT,
    expected_return_pct REAL, confidence REAL, weights TEXT, contributors TEXT,
    stage TEXT DEFAULT 'revised',
    analysis_point INTEGER DEFAULT 0, base_price REAL,
    UNIQUE(cycle_date, symbol, stage)
);
CREATE TABLE IF NOT EXISTS horizon_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, analysis_point INTEGER, symbol TEXT, source TEXT,
    horizon TEXT, base_price REAL, target_price REAL,
    expected_return_pct REAL, direction TEXT, confidence REAL,
    target_date TEXT, actual_price REAL, hit INTEGER, abs_error_pct REAL,
    evaluated_at TEXT, created_at TEXT,
    UNIQUE(cycle_date, analysis_point, symbol, source, horizon)
);
CREATE TABLE IF NOT EXISTS actuals (
    cycle_date TEXT, symbol TEXT, actual_return_pct REAL,
    PRIMARY KEY (cycle_date, symbol)
);
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, symbol TEXT, predictor TEXT,
    predicted_direction TEXT, actual_direction TEXT, hit INTEGER, abs_error REAL,
    UNIQUE(cycle_date, symbol, predictor)
);
CREATE TABLE IF NOT EXISTS weights (
    predictor TEXT PRIMARY KEY, weight REAL, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS improver_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, improver TEXT, action TEXT, detail TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS confidence (
    cycle_date TEXT PRIMARY KEY, overall_accuracy REAL, rolling_accuracy REAL,
    calibrated_confidence REAL, trade_ready INTEGER, detail TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS predictor_params (
    predictor TEXT PRIMARY KEY, scale REAL, sign REAL,
    flipped_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS stock_discoveries (
    symbol TEXT PRIMARY KEY, name TEXT, market TEXT,
    mentions INTEGER DEFAULT 1, first_seen TEXT, last_seen TEXT,
    dismissed INTEGER DEFAULT 0, reason TEXT
);
CREATE TABLE IF NOT EXISTS harness_debates (
    cycle_date TEXT, analysis_point INTEGER, symbol TEXT,
    draft_return_pct REAL, draft_confidence REAL,
    final_return_pct REAL, final_confidence REAL, final_direction TEXT,
    bull_case TEXT, bear_case TEXT, verdict TEXT, created_at TEXT,
    PRIMARY KEY (cycle_date, analysis_point, symbol)
);
CREATE TABLE IF NOT EXISTS harness_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, symbol TEXT, lesson TEXT, abs_error REAL, created_at TEXT
);
CREATE TABLE IF NOT EXISTS earnings_events (
    symbol TEXT NOT NULL,
    event_date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    surprise_pct REAL,
    actual_eps REAL,
    expected_eps REAL,
    sector TEXT,
    source TEXT,
    created_at TEXT,
    PRIMARY KEY (symbol, event_date)
);
CREATE TABLE IF NOT EXISTS insider_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    filed_date TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    filer TEXT,
    role TEXT,
    transaction_type TEXT,
    shares REAL,
    price_per_share REAL,
    total_value REAL,
    is_scheduled INTEGER DEFAULT 0,
    form_type TEXT,
    created_at TEXT,
    UNIQUE(symbol, transaction_date, filer, transaction_type)
);
CREATE TABLE IF NOT EXISTS event_car_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    event_date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    sector TEXT,
    surprise_pct REAL,
    day_offset INTEGER NOT NULL,
    car REAL NOT NULL,
    created_at TEXT,
    UNIQUE(symbol, event_date, day_offset)
);
CREATE TABLE IF NOT EXISTS event_patterns (
    event_type TEXT NOT NULL,
    sector TEXT NOT NULL,
    avg_car_d1 REAL,
    avg_car_d5 REAL,
    avg_car_d10 REAL,
    hit_rate REAL,
    sample_count INTEGER,
    updated_at TEXT,
    PRIMARY KEY (event_type, sector)
);
CREATE TABLE IF NOT EXISTS fundamentals (
    symbol TEXT PRIMARY KEY,
    as_of TEXT,
    pe REAL, forward_pe REAL, pb REAL, ps REAL,
    roe REAL, debt_to_equity REAL, profit_margin REAL,
    current_ratio REAL, beta REAL, dividend_yield REAL,
    source TEXT, updated_at TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """기존 DB에 새 컬럼이 없으면 추가(하위호환)."""
        for table in ("predictions", "ensemble_predictions"):
            cols = {r["name"] for r in self.conn.execute(
                f"PRAGMA table_info({table})").fetchall()}
            if "stage" not in cols:
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN stage TEXT DEFAULT 'revised'")
            if "analysis_point" not in cols:
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN analysis_point INTEGER DEFAULT 0")
            if "base_price" not in cols:
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN base_price REAL")
        news_cols = {r["name"] for r in self.conn.execute(
            "PRAGMA table_info(news)").fetchall()}
        if "symbol" not in news_cols:
            self.conn.execute("ALTER TABLE news ADD COLUMN symbol TEXT DEFAULT ''")

    def close(self) -> None:
        self.conn.close()

    # ---- 뉴스/애널리스트 ----
    def save_news(self, cycle_date: str, items: list[NewsItem]) -> None:
        self.conn.executemany(
            "INSERT INTO news (cycle_date, market, source, title, summary, url,"
            " published_at, sentiment, symbol, collected_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(cycle_date, n.market, n.source, n.title, n.summary, n.url,
              n.published_at, n.sentiment, n.symbol, _now()) for n in items],
        )
        self.conn.commit()

    def save_analyst_views(self, cycle_date: str, views: list[AnalystView]) -> None:
        self.conn.executemany(
            "INSERT INTO analyst_views (cycle_date, market, firm, symbol, rating,"
            " target_return_pct) VALUES (?,?,?,?,?,?)",
            [(cycle_date, v.market, v.firm, v.symbol, v.rating,
              v.target_return_pct) for v in views],
        )
        self.conn.commit()

    @staticmethod
    def _row_to_news(r) -> NewsItem:
        return NewsItem(r["market"], r["source"], r["title"], r["summary"],
                        r["url"], r["published_at"], r["sentiment"],
                        r["symbol"] if "symbol" in r.keys() else "")

    def news_for_market(self, cycle_date: str, market: str) -> list[NewsItem]:
        """시장 전반 뉴스(symbol='')만."""
        rows = self.conn.execute(
            "SELECT * FROM news WHERE cycle_date=? AND market=? AND"
            " (symbol IS NULL OR symbol='')", (cycle_date, market),
        ).fetchall()
        return [self._row_to_news(r) for r in rows]

    def news_for_symbol(self, cycle_date: str, market: str,
                        symbol: str) -> list[NewsItem]:
        """해당 종목용 입력: 시장 전반 + 그 종목 직접 뉴스."""
        rows = self.conn.execute(
            "SELECT * FROM news WHERE cycle_date=? AND market=? AND"
            " (symbol IS NULL OR symbol='' OR symbol=?)",
            (cycle_date, market, symbol),
        ).fetchall()
        return [self._row_to_news(r) for r in rows]

    def news_for_cycle(self, cycle_date: str) -> list[NewsItem]:
        rows = self.conn.execute(
            "SELECT * FROM news WHERE cycle_date=?", (cycle_date,)
        ).fetchall()
        return [self._row_to_news(r) for r in rows]

    def analyst_views_for_symbol(self, cycle_date: str, symbol: str) -> list[AnalystView]:
        rows = self.conn.execute(
            "SELECT * FROM analyst_views WHERE cycle_date=? AND symbol=?",
            (cycle_date, symbol),
        ).fetchall()
        return [AnalystView(r["market"], r["firm"], r["symbol"], r["rating"],
                            r["target_return_pct"]) for r in rows]

    # ---- 예측 ----
    def save_prediction(self, p: Prediction, stage: str = "revised",
                        analysis_point: int = 0,
                        base_price: float | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO predictions (cycle_date, symbol, predictor,"
            " direction, expected_return_pct, confidence, rationale, stage,"
            " analysis_point, base_price)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (p.cycle_date, p.symbol, p.predictor, p.direction,
             p.expected_return_pct, p.confidence, p.rationale, stage,
             analysis_point, base_price),
        )
        self.conn.commit()

    def save_ensemble(self, e: EnsemblePrediction, stage: str = "revised",
                      analysis_point: int = 0,
                      base_price: float | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ensemble_predictions (cycle_date, symbol,"
            " direction, expected_return_pct, confidence, weights, contributors,"
            " stage, analysis_point, base_price) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (e.cycle_date, e.symbol, e.direction, e.expected_return_pct,
             e.confidence, json.dumps(e.weights), json.dumps(e.contributors),
             stage, analysis_point, base_price),
        )
        self.conn.commit()

    # ---- 기간별 목표주가 (horizon targets) ----
    def save_horizon_targets(self, cycle_date: str, analysis_point: int,
                             symbol: str, source: str, rows: list[dict]) -> None:
        now = _now()
        self.conn.executemany(
            "INSERT OR REPLACE INTO horizon_targets (cycle_date, analysis_point,"
            " symbol, source, horizon, base_price, target_price,"
            " expected_return_pct, direction, confidence, target_date,"
            " actual_price, hit, abs_error_pct, evaluated_at, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [(cycle_date, analysis_point, symbol, source, r["horizon"],
              r["base_price"], r["target_price"], r["expected_return_pct"],
              r["direction"], r["confidence"], r["target_date"],
              None, None, None, None, now) for r in rows],
        )
        self.conn.commit()

    def horizons_for_cycle(self, cycle_date: str,
                           source: str = "ensemble") -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM horizon_targets WHERE cycle_date=? AND source=?"
            " ORDER BY symbol, analysis_point", (cycle_date, source),
        ).fetchall()
        return [dict(r) for r in rows]

    def pending_horizon_targets(self, today: str) -> list[dict]:
        """만기가 도래(target_date<=today)했으나 아직 평가 안 된 항목."""
        rows = self.conn.execute(
            "SELECT * FROM horizon_targets WHERE target_date<=? AND"
            " actual_price IS NULL", (today,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_horizon_actual(self, target_id: int, actual_price: float,
                              hit: bool, abs_error_pct: float) -> None:
        self.conn.execute(
            "UPDATE horizon_targets SET actual_price=?, hit=?, abs_error_pct=?,"
            " evaluated_at=? WHERE id=?",
            (actual_price, int(hit), abs_error_pct, _now(), target_id),
        )
        self.conn.commit()

    def horizon_accuracy(self) -> list[dict]:
        """기간별 평가 누적 정확도(만기 도래분 기준)."""
        rows = self.conn.execute(
            "SELECT horizon, COUNT(*) AS total, SUM(hit) AS hits,"
            " AVG(abs_error_pct) AS mae FROM horizon_targets"
            " WHERE source='ensemble' AND actual_price IS NOT NULL"
            " GROUP BY horizon", ).fetchall()
        return [dict(r) for r in rows]

    def predictions_for_cycle(self, cycle_date: str,
                              stage: str = "revised") -> list[Prediction]:
        rows = self.conn.execute(
            "SELECT * FROM predictions WHERE cycle_date=? AND stage=?",
            (cycle_date, stage),
        ).fetchall()
        return [Prediction(r["cycle_date"], r["symbol"], r["predictor"],
                           r["direction"], r["expected_return_pct"],
                           r["confidence"], r["rationale"]) for r in rows]

    def ensemble_for_cycle(self, cycle_date: str,
                           stage: str = "revised") -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM ensemble_predictions WHERE cycle_date=? AND stage=?",
            (cycle_date, stage),
        ).fetchall()
        out = []
        for r in rows:
            keys = r.keys()
            out.append({
                "cycle_date": r["cycle_date"], "symbol": r["symbol"],
                "direction": r["direction"],
                "expected_return_pct": r["expected_return_pct"],
                "confidence": r["confidence"],
                "weights": json.loads(r["weights"] or "{}"),
                "contributors": json.loads(r["contributors"] or "{}"),
                "analysis_point": r["analysis_point"] if "analysis_point" in keys else 0,
                "base_price": r["base_price"] if "base_price" in keys else None,
            })
        return out

    # ---- 실제값 / 평가 ----
    def save_actual(self, a: Actual) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO actuals (cycle_date, symbol, actual_return_pct)"
            " VALUES (?,?,?)", (a.cycle_date, a.symbol, a.actual_return_pct),
        )
        self.conn.commit()

    def save_evaluation(self, e: Evaluation) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO evaluations (cycle_date, symbol, predictor,"
            " predicted_direction, actual_direction, hit, abs_error)"
            " VALUES (?,?,?,?,?,?,?)",
            (e.cycle_date, e.symbol, e.predictor, e.predicted_direction,
             e.actual_direction, int(e.hit), e.abs_error),
        )
        self.conn.commit()

    def actual(self, cycle_date: str, symbol: str) -> float | None:
        row = self.conn.execute(
            "SELECT actual_return_pct FROM actuals WHERE cycle_date=? AND symbol=?",
            (cycle_date, symbol),
        ).fetchone()
        return row["actual_return_pct"] if row else None

    # ---- 가중치 ----
    def get_weights(self) -> dict[str, float]:
        rows = self.conn.execute("SELECT predictor, weight FROM weights").fetchall()
        return {r["predictor"]: r["weight"] for r in rows}

    def set_weight(self, predictor: str, weight: float) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO weights (predictor, weight, updated_at)"
            " VALUES (?,?,?)", (predictor, weight, _now()),
        )
        self.conn.commit()

    # ---- 예측가 자가보정 파라미터 (발전 에이전트가 학습) ----
    def get_predictor_params(self) -> dict[str, tuple[float, float]]:
        """predictor -> (scale, sign). 예측 시 사용. 미설정 시 (1.0, 1.0) 기본."""
        rows = self.conn.execute(
            "SELECT predictor, scale, sign FROM predictor_params"
        ).fetchall()
        return {r["predictor"]: (r["scale"], r["sign"]) for r in rows}

    def get_predictor_meta(self) -> dict[str, dict]:
        """발전 에이전트용: scale·sign·flipped_at 전체."""
        rows = self.conn.execute(
            "SELECT predictor, scale, sign, flipped_at FROM predictor_params"
        ).fetchall()
        return {r["predictor"]: {"scale": r["scale"], "sign": r["sign"],
                                 "flipped_at": r["flipped_at"]} for r in rows}

    def set_predictor_param(self, predictor: str, scale: float, sign: float,
                            flipped_at: str | None = None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO predictor_params (predictor, scale, sign,"
            " flipped_at, updated_at) VALUES (?,?,?,?,?)",
            (predictor, scale, sign, flipped_at, _now()),
        )
        self.conn.commit()

    def predictor_accuracy_since(self, predictor: str,
                                 since_cycle: str | None) -> tuple[int, int]:
        """since_cycle 이후(미포함) 사이클의 (적중수, 전체수).

        부호 반전 직후 '새 부호로 쌓인 증거'만 보고 재반전을 결정하기 위함.
        since_cycle 이 None 이면 전체 이력 기준.
        """
        if since_cycle:
            rows = self.conn.execute(
                "SELECT hit FROM evaluations WHERE predictor=? AND cycle_date>?",
                (predictor, since_cycle),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT hit FROM evaluations WHERE predictor=?", (predictor,)
            ).fetchall()
        return sum(r["hit"] for r in rows), len(rows)

    def recent_pred_actual(self, predictor: str, window: int,
                           stage: str = "ap3_us_open") -> list[tuple[float, float]]:
        """최근 window 사이클의 (예측수익률, 실제수익률) 쌍."""
        rows = self.conn.execute(
            "SELECT p.expected_return_pct AS pred, a.actual_return_pct AS act"
            " FROM predictions p JOIN actuals a"
            " ON p.cycle_date=a.cycle_date AND p.symbol=a.symbol"
            " WHERE p.predictor=? AND p.stage=? AND p.cycle_date IN ("
            "   SELECT DISTINCT cycle_date FROM actuals ORDER BY cycle_date"
            "   DESC LIMIT ?)", (predictor, stage, window),
        ).fetchall()
        return [(r["pred"], r["act"]) for r in rows]

    # ---- 발전 로그 ----
    def log_improver(self, cycle_date: str, improver: str, action: str, detail: str) -> None:
        self.conn.execute(
            "INSERT INTO improver_logs (cycle_date, improver, action, detail,"
            " created_at) VALUES (?,?,?,?,?)",
            (cycle_date, improver, action, detail, _now()),
        )
        self.conn.commit()

    def recent_improver_logs(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM improver_logs ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- 신뢰도 ----
    def save_confidence(self, cycle_date: str, overall: float, rolling: float,
                        calibrated: float, trade_ready: bool, detail: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO confidence (cycle_date, overall_accuracy,"
            " rolling_accuracy, calibrated_confidence, trade_ready, detail,"
            " created_at) VALUES (?,?,?,?,?,?,?)",
            (cycle_date, overall, rolling, calibrated, int(trade_ready),
             detail, _now()),
        )
        self.conn.commit()

    def latest_confidence(self) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM confidence ORDER BY cycle_date DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def confidence_for_cycle(self, cycle_date: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM confidence WHERE cycle_date=?", (cycle_date,)
        ).fetchone()
        return dict(row) if row else None

    # ---- 일일 리포트 ----
    def save_report(self, cycle_date: str, markdown: str, summary: dict) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO daily_reports (cycle_date, markdown, summary,"
            " created_at) VALUES (?,?,?,?)",
            (cycle_date, markdown, json.dumps(summary, ensure_ascii=False), _now()),
        )
        self.conn.commit()

    def get_report(self, cycle_date: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM daily_reports WHERE cycle_date=?", (cycle_date,)
        ).fetchone()
        if not row:
            return None
        out = dict(row)
        out["summary"] = json.loads(out["summary"] or "{}")
        return out

    def report_list(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT cycle_date, summary, created_at FROM daily_reports"
            " ORDER BY cycle_date DESC"
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["summary"] = json.loads(d["summary"] or "{}")
            out.append(d)
        return out

    def improver_logs_for_cycle(self, cycle_date: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM improver_logs WHERE cycle_date=? ORDER BY id", (cycle_date,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- 통계/리포트 ----
    def predictor_accuracy(self, predictor: str, window: int | None = None) -> tuple[int, int]:
        """(적중수, 전체수) 반환. window 지정 시 최근 window 사이클만."""
        if window:
            rows = self.conn.execute(
                "SELECT hit FROM evaluations WHERE predictor=? AND cycle_date IN ("
                " SELECT DISTINCT cycle_date FROM evaluations ORDER BY cycle_date"
                " DESC LIMIT ?) ", (predictor, window),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT hit FROM evaluations WHERE predictor=?", (predictor,)
            ).fetchall()
        hits = sum(r["hit"] for r in rows)
        return hits, len(rows)

    def all_predictors(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT predictor FROM evaluations"
        ).fetchall()
        return [r["predictor"] for r in rows]

    def cycle_dates(self) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT cycle_date FROM ensemble_predictions ORDER BY cycle_date"
        ).fetchall()
        return [r["cycle_date"] for r in rows]

    def accuracy_history(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT cycle_date, overall_accuracy, rolling_accuracy,"
            " calibrated_confidence, trade_ready FROM confidence ORDER BY cycle_date"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- 스케줄러 ----
    def slot_done(self, cycle_date: str, point_id: int) -> bool:
        """분석 시점 완료 여부를 기존 데이터로 판단한다.

        시점 1~3(예측): 해당 analysis_point 의 앙상블 예측이 존재
        시점 4(평가·발전): 신뢰도 기록이 존재
        """
        if point_id in (1, 2, 3):
            return bool(self.conn.execute(
                "SELECT 1 FROM ensemble_predictions"
                " WHERE cycle_date=? AND analysis_point=? LIMIT 1",
                (cycle_date, point_id)).fetchone())
        if point_id == 4:
            return bool(self.conn.execute(
                "SELECT 1 FROM confidence WHERE cycle_date=? LIMIT 1",
                (cycle_date,)).fetchone())
        return False

    def log_scheduler(self, cycle_date: str, slot: int, status: str,
                      detail: str = "") -> None:
        self.conn.execute(
            "INSERT INTO scheduler_log (cycle_date, slot, status, detail, ran_at)"
            " VALUES (?,?,?,?,?)", (cycle_date, slot, status, detail, _now()),
        )
        self.conn.commit()

    def scheduler_history(self, limit: int = 30) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scheduler_log ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- 이벤트 카탈로그 (실적·내부자거래·CAR 패턴) ----

    def save_earnings_events(self, events: list, sector: str = "") -> None:
        """실적 발표 이벤트 upsert (기존 레코드는 덮어씀)."""
        if not events:
            return
        now = _now()
        self.conn.executemany(
            "INSERT OR REPLACE INTO earnings_events"
            " (symbol, event_date, event_type, surprise_pct, actual_eps,"
            " expected_eps, sector, source, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [(e.symbol, e.event_date, e.event_type, e.surprise_pct,
              e.actual_eps, e.expected_eps, sector, e.source, now)
             for e in events],
        )
        self.conn.commit()

    def recent_earnings_for_symbol(
            self, symbol: str, days_back: int = 20) -> list[dict]:
        """symbol의 최근 days_back 일 이내 실적 이벤트(최신순)."""
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow().date() - timedelta(days=days_back)).isoformat()
        rows = self.conn.execute(
            "SELECT * FROM earnings_events WHERE symbol=? AND event_date>=?"
            " ORDER BY event_date DESC",
            (symbol, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_insider_trades(self, trades: list) -> None:
        """내부자 거래 upsert (동일 symbol+date+filer+type 은 무시)."""
        if not trades:
            return
        now = _now()
        self.conn.executemany(
            "INSERT OR IGNORE INTO insider_trades"
            " (symbol, filed_date, transaction_date, filer, role,"
            " transaction_type, shares, price_per_share, total_value,"
            " is_scheduled, form_type, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [(t.symbol, t.filed_date, t.transaction_date, t.filer, t.role,
              t.transaction_type, t.shares, t.price_per_share, t.total_value,
              int(t.is_scheduled), t.form_type, now)
             for t in trades],
        )
        self.conn.commit()

    def recent_insiders_for_symbol(
            self, symbol: str, days_back: int = 45) -> list[dict]:
        """symbol의 최근 days_back 일 이내 내부자 거래(신고일 기준, 최신순)."""
        from datetime import datetime, timedelta
        cutoff = (datetime.utcnow().date() - timedelta(days=days_back)).isoformat()
        rows = self.conn.execute(
            "SELECT * FROM insider_trades WHERE symbol=? AND filed_date>=?"
            " ORDER BY filed_date DESC",
            (symbol, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    def save_event_car_records(
            self, symbol: str, event_date: str, event_type: str,
            sector: str, surprise_pct: float,
            car: dict[int, float]) -> None:
        """이벤트별 일자별 CAR 저장(upsert)."""
        if not car:
            return
        now = _now()
        self.conn.executemany(
            "INSERT OR REPLACE INTO event_car_records"
            " (symbol, event_date, event_type, sector, surprise_pct,"
            " day_offset, car, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [(symbol, event_date, event_type, sector, surprise_pct,
              offset, val, now)
             for offset, val in car.items()],
        )
        self.conn.commit()

    def event_pattern(self, event_type: str, sector: str) -> dict | None:
        """특정 (event_type, sector) 조합의 집계 패턴. 없으면 None."""
        row = self.conn.execute(
            "SELECT * FROM event_patterns WHERE event_type=? AND sector=?",
            (event_type, sector),
        ).fetchone()
        return dict(row) if row else None

    def update_event_patterns(self) -> int:
        """event_car_records 에서 (event_type, sector) 별 패턴을 집계·갱신.

        반환: 업데이트된 패턴 수
        """
        rows = self.conn.execute(
            "SELECT event_type, sector, surprise_pct,"
            " MAX(CASE WHEN day_offset=1  THEN car END) AS car_d1,"
            " MAX(CASE WHEN day_offset=5  THEN car END) AS car_d5,"
            " MAX(CASE WHEN day_offset=10 THEN car END) AS car_d10"
            " FROM event_car_records"
            " GROUP BY symbol, event_date, event_type, sector, surprise_pct"
        ).fetchall()

        if not rows:
            return 0

        from .events import aggregate_car_records
        records = [
            {"event_type": r["event_type"], "sector": r["sector"],
             "surprise_pct": r["surprise_pct"],
             "car_d1": r["car_d1"], "car_d5": r["car_d5"],
             "car_d10": r["car_d10"]}
            for r in rows
        ]
        patterns = aggregate_car_records(records)

        now = _now()
        self.conn.executemany(
            "INSERT OR REPLACE INTO event_patterns"
            " (event_type, sector, avg_car_d1, avg_car_d5, avg_car_d10,"
            " hit_rate, sample_count, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [(etype, sector, p["avg_car_d1"], p["avg_car_d5"], p["avg_car_d10"],
              p["hit_rate"], p["sample_count"], now)
             for (etype, sector), p in patterns.items()],
        )
        self.conn.commit()
        return len(patterns)

    def all_event_patterns(self) -> list[dict]:
        """대시보드용 전체 이벤트 패턴 테이블."""
        rows = self.conn.execute(
            "SELECT * FROM event_patterns ORDER BY event_type, sector"
        ).fetchall()
        return [dict(r) for r in rows]

    def earnings_events_summary(self, limit: int = 30) -> list[dict]:
        """최근 실적 이벤트 요약(대시보드용)."""
        rows = self.conn.execute(
            "SELECT * FROM earnings_events ORDER BY event_date DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def recent_earnings_window(self, ref_date: str,
                               days_back: int = 5) -> list[dict]:
        """ref_date 기준 과거 days_back 일 이내(ref_date 이하) 모든 실적 이벤트.

        섹터 전이 신호용: 같은 섹터 동료의 최근 실적을 한 번에 가져온다.
        """
        from datetime import date, timedelta
        try:
            cutoff = (date.fromisoformat(ref_date) -
                      timedelta(days=days_back)).isoformat()
        except ValueError:
            return []
        rows = self.conn.execute(
            "SELECT * FROM earnings_events WHERE event_date>=? AND event_date<=?"
            " ORDER BY event_date DESC",
            (cutoff, ref_date),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- 펀더멘털 (밸류·퀄리티 팩터용) ----

    def save_fundamentals(self, f) -> None:
        """재무 스냅샷 upsert (종목당 최신 1건)."""
        if f is None:
            return
        self.conn.execute(
            "INSERT OR REPLACE INTO fundamentals"
            " (symbol, as_of, pe, forward_pe, pb, ps, roe, debt_to_equity,"
            " profit_margin, current_ratio, beta, dividend_yield, source,"
            " updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f.symbol, f.as_of, f.pe, f.forward_pe, f.pb, f.ps, f.roe,
             f.debt_to_equity, f.profit_margin, f.current_ratio, f.beta,
             f.dividend_yield, f.source, _now()),
        )
        self.conn.commit()

    def fundamentals_for(self, symbol: str) -> dict | None:
        """종목의 최신 재무 스냅샷. 없으면 None."""
        row = self.conn.execute(
            "SELECT * FROM fundamentals WHERE symbol=?", (symbol,)
        ).fetchone()
        return dict(row) if row else None

    def all_fundamentals(self) -> list[dict]:
        """대시보드용 전체 재무 스냅샷."""
        rows = self.conn.execute(
            "SELECT * FROM fundamentals ORDER BY symbol"
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- 신규 종목 발견 ----
    def upsert_discovery(self, symbol: str, name: str, market: str,
                         reason: str) -> None:
        now = _now()
        existing = self.conn.execute(
            "SELECT mentions, dismissed FROM stock_discoveries WHERE symbol=?",
            (symbol,),
        ).fetchone()
        if existing:
            if existing["dismissed"]:
                return  # 사용자가 무시한 종목은 재등록 안 함
            self.conn.execute(
                "UPDATE stock_discoveries SET mentions=mentions+1, last_seen=?,"
                " reason=? WHERE symbol=?",
                (now, reason, symbol),
            )
        else:
            self.conn.execute(
                "INSERT INTO stock_discoveries (symbol, name, market, mentions,"
                " first_seen, last_seen, dismissed, reason)"
                " VALUES (?,?,?,1,?,?,0,?)",
                (symbol, name, market, now, now, reason),
            )
        self.conn.commit()

    def get_discoveries(self, include_dismissed: bool = False) -> list[dict]:
        sql = "SELECT * FROM stock_discoveries"
        if not include_dismissed:
            sql += " WHERE dismissed=0"
        sql += " ORDER BY mentions DESC, last_seen DESC"
        return [dict(r) for r in self.conn.execute(sql).fetchall()]

    def dismiss_discovery(self, symbol: str) -> None:
        self.conn.execute(
            "UPDATE stock_discoveries SET dismissed=1 WHERE symbol=?", (symbol,)
        )
        self.conn.commit()

    # ---- 하네스 토론 / 회고 교훈 ----
    def save_debate(self, cycle_date: str, analysis_point: int, symbol: str,
                    draft_return: float, draft_conf: float,
                    final_return: float, final_conf: float,
                    final_dir: str, bull: str, bear: str, verdict: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO harness_debates (cycle_date, analysis_point,"
            " symbol, draft_return_pct, draft_confidence, final_return_pct,"
            " final_confidence, final_direction, bull_case, bear_case, verdict,"
            " created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (cycle_date, analysis_point, symbol, draft_return, draft_conf,
             final_return, final_conf, final_dir, bull, bear, verdict, _now()),
        )
        self.conn.commit()

    def debates_for_cycle(self, cycle_date: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM harness_debates WHERE cycle_date=?"
            " ORDER BY symbol, analysis_point", (cycle_date,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_lesson(self, cycle_date: str, symbol: str, lesson: str,
                   abs_error: float) -> None:
        self.conn.execute(
            "INSERT INTO harness_lessons (cycle_date, symbol, lesson, abs_error,"
            " created_at) VALUES (?,?,?,?,?)",
            (cycle_date, symbol, lesson, abs_error, _now()),
        )
        self.conn.commit()

    def recent_lessons(self, symbol: str | None = None,
                       limit: int = 5) -> list[str]:
        """심판 프롬프트에 주입할 최근 회고 교훈. 종목별 우선, 부족하면 전체."""
        if symbol:
            rows = self.conn.execute(
                "SELECT lesson FROM harness_lessons WHERE symbol=?"
                " ORDER BY id DESC LIMIT ?", (symbol, limit),
            ).fetchall()
            if rows:
                return [r["lesson"] for r in rows]
        rows = self.conn.execute(
            "SELECT lesson FROM harness_lessons ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [r["lesson"] for r in rows]

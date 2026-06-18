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
CREATE TABLE IF NOT EXISTS news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, market TEXT, source TEXT, title TEXT,
    summary TEXT, url TEXT, published_at TEXT, sentiment REAL,
    collected_at TEXT
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
    UNIQUE(cycle_date, symbol, predictor)
);
CREATE TABLE IF NOT EXISTS ensemble_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_date TEXT, symbol TEXT, direction TEXT,
    expected_return_pct REAL, confidence REAL, weights TEXT, contributors TEXT,
    UNIQUE(cycle_date, symbol)
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
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Storage:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- 뉴스/애널리스트 ----
    def save_news(self, cycle_date: str, items: list[NewsItem]) -> None:
        self.conn.executemany(
            "INSERT INTO news (cycle_date, market, source, title, summary, url,"
            " published_at, sentiment, collected_at) VALUES (?,?,?,?,?,?,?,?,?)",
            [(cycle_date, n.market, n.source, n.title, n.summary, n.url,
              n.published_at, n.sentiment, _now()) for n in items],
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

    def news_for_market(self, cycle_date: str, market: str) -> list[NewsItem]:
        rows = self.conn.execute(
            "SELECT * FROM news WHERE cycle_date=? AND market=?",
            (cycle_date, market),
        ).fetchall()
        return [NewsItem(r["market"], r["source"], r["title"], r["summary"],
                         r["url"], r["published_at"], r["sentiment"]) for r in rows]

    def analyst_views_for_symbol(self, cycle_date: str, symbol: str) -> list[AnalystView]:
        rows = self.conn.execute(
            "SELECT * FROM analyst_views WHERE cycle_date=? AND symbol=?",
            (cycle_date, symbol),
        ).fetchall()
        return [AnalystView(r["market"], r["firm"], r["symbol"], r["rating"],
                            r["target_return_pct"]) for r in rows]

    # ---- 예측 ----
    def save_prediction(self, p: Prediction) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO predictions (cycle_date, symbol, predictor,"
            " direction, expected_return_pct, confidence, rationale)"
            " VALUES (?,?,?,?,?,?,?)",
            (p.cycle_date, p.symbol, p.predictor, p.direction,
             p.expected_return_pct, p.confidence, p.rationale),
        )
        self.conn.commit()

    def save_ensemble(self, e: EnsemblePrediction) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO ensemble_predictions (cycle_date, symbol,"
            " direction, expected_return_pct, confidence, weights, contributors)"
            " VALUES (?,?,?,?,?,?,?)",
            (e.cycle_date, e.symbol, e.direction, e.expected_return_pct,
             e.confidence, json.dumps(e.weights), json.dumps(e.contributors)),
        )
        self.conn.commit()

    def predictions_for_cycle(self, cycle_date: str) -> list[Prediction]:
        rows = self.conn.execute(
            "SELECT * FROM predictions WHERE cycle_date=?", (cycle_date,)
        ).fetchall()
        return [Prediction(r["cycle_date"], r["symbol"], r["predictor"],
                           r["direction"], r["expected_return_pct"],
                           r["confidence"], r["rationale"]) for r in rows]

    def ensemble_for_cycle(self, cycle_date: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM ensemble_predictions WHERE cycle_date=?", (cycle_date,)
        ).fetchall()
        out = []
        for r in rows:
            out.append({
                "cycle_date": r["cycle_date"], "symbol": r["symbol"],
                "direction": r["direction"],
                "expected_return_pct": r["expected_return_pct"],
                "confidence": r["confidence"],
                "weights": json.loads(r["weights"] or "{}"),
                "contributors": json.loads(r["contributors"] or "{}"),
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

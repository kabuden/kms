"""매일 자동 분석 스케줄러 (표준 라이브러리만 사용).

한국장을 중심으로 한 사이클(거래일 D)을 4개 시점에 자동 실행한다(KST 기준).
  ① 08:00 KST  한국장 개장 전 — 1차 예측
  ② 16:00 KST  한국장 마감 후 — 재예측
  ③ 23:30 KST  미국장 개장 후 — 공식 예측
  ④ 06:30 KST(D+1) 미국장 마감 후 — 평가 + 발전 + 장기예측 정산

각 시점의 실제 실행 시각은 KST 시각에서 9시간을 뺀 UTC 로 계산한다. 주말(토·일)
거래일은 건너뛰며, 서버가 꺼져 있던 동안 지나간 시점은 재시작 시 따라잡는다.
"""
from __future__ import annotations

import threading
import traceback
from datetime import datetime, time, timedelta, timezone
from typing import Callable

from .config import ANALYSIS_POINTS, KST_OFFSET_HOURS, SETTINGS, AnalysisPoint
from .orchestrator import Orchestrator
from .storage import Storage

_KST = timezone(timedelta(hours=KST_OFFSET_HOURS))

# 다음 체크까지 대기 시간(초)
_POLL_SECONDS = 60


def _is_trading_day(d) -> bool:
    """월~금을 거래일로 간주(공휴일 미처리)."""
    return d.weekday() < 5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _due_utc(cycle_date, point: AnalysisPoint) -> datetime:
    """거래일 D 의 한 시점이 실행돼야 할 UTC 시각."""
    run_day = cycle_date + timedelta(days=point.day_offset)
    kst_dt = datetime.combine(
        run_day, time(point.kst_hour, point.kst_minute), tzinfo=_KST)
    return kst_dt.astimezone(timezone.utc)


class DailyScheduler:
    """백그라운드 스레드로 매일 4시점을 정해진 시각에 자동 실행한다."""

    def __init__(self,
                 on_point_done: Callable[[str, int, dict], None] | None = None):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._on_point_done = on_point_done
        self._lock = threading.Lock()  # 중복 실행 방지

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="StockScheduler", daemon=True)
        self._thread.start()
        print("📅 스케줄러 시작 (한국장 기준 08:00 / 16:00 / 23:30 / 익일 06:30 KST)")

    def stop(self) -> None:
        self._stop.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._catchup()
            except Exception:
                pass  # 루프 사망 방지
            self._stop.wait(timeout=_POLL_SECONDS)

    def _candidate_cycle_dates(self):
        """현재 KST 기준 활성 사이클 후보(최근 3일).

        주말 동안 서버가 꺼져 있어도 금요일 사이클의 ④(토요일 새벽 KST)을
        놓치지 않도록 며칠 거슬러 본다. 완료된 시점은 slot_done 으로 건너뛴다.
        """
        kst_today = _utc_now().astimezone(_KST).date()
        return [kst_today - timedelta(days=n) for n in (3, 2, 1, 0)]

    def _catchup(self) -> None:
        """시간이 지났으나 아직 안 된 시점을 순서대로 실행한다."""
        now = _utc_now()
        for cycle_date in self._candidate_cycle_dates():
            if not _is_trading_day(cycle_date):
                continue
            date_str = cycle_date.isoformat()
            for point in ANALYSIS_POINTS:
                if now < _due_utc(cycle_date, point):
                    continue  # 아직 시간 안 됨
                self._run_point_if_needed(date_str, point)

    def _run_point_if_needed(self, cycle_date: str, point: AnalysisPoint) -> None:
        store = Storage(SETTINGS.db_path)
        try:
            if store.slot_done(cycle_date, point.id):
                return
        finally:
            store.close()

        with self._lock:
            store = Storage(SETTINGS.db_path)
            try:
                if store.slot_done(cycle_date, point.id):
                    return
                self._execute(store, cycle_date, point)
            finally:
                store.close()

    def _execute(self, store: Storage, cycle_date: str,
                 point: AnalysisPoint) -> None:
        print(f"[스케줄러] {cycle_date} {point.label} 시작...")
        try:
            orch = Orchestrator(store)
            result = orch.run_analysis_point(cycle_date, point.id)
            store.log_scheduler(cycle_date, point.id, "ok", point.label)
            print(f"[스케줄러] {cycle_date} {point.label} 완료")
            if self._on_point_done:
                self._on_point_done(cycle_date, point.id, result)
        except Exception as exc:
            detail = traceback.format_exc(limit=5)
            store.log_scheduler(cycle_date, point.id, "error", str(exc))
            print(f"[스케줄러] {cycle_date} {point.label} 오류: {exc}\n{detail}")


# ------------------------------------------------------------------ #
# 스케줄 상태 조회 (웹 API 용)
# ------------------------------------------------------------------ #

def schedule_status(store: Storage) -> dict:
    """현재 활성 사이클(오늘 한국 날짜)의 시점 현황 + 최근 실행 로그."""
    now = _utc_now()
    kst_now = now.astimezone(_KST)
    cycle_date = kst_now.date()
    date_str = cycle_date.isoformat()
    is_trading = _is_trading_day(cycle_date)

    points = []
    for p in ANALYSIS_POINTS:
        due = _due_utc(cycle_date, p)
        points.append({
            "point": p.id,
            "label": p.label,
            "role": p.role,
            "note": p.note,
            "kst": f"{p.kst_hour:02d}:{p.kst_minute:02d}"
                   + ("(D+1)" if p.day_offset else ""),
            "due_utc": due.isoformat(),
            "past_due": now >= due,
            "done": store.slot_done(date_str, p.id) if is_trading else None,
        })

    return {
        "today": date_str,
        "is_trading_day": is_trading,
        "now_kst": kst_now.strftime("%H:%M"),
        "now_utc": now.strftime("%H:%M"),
        "points": points,
        "recent_log": store.scheduler_history(40),
    }

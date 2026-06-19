"""매일 자동 예측 스케줄러 (표준 라이브러리만 사용).

일정 (UTC):
  08:00  슬롯 1 — 기본 예측  (한국 장 마감 후, 미국 장 개장 전)
  14:00  슬롯 2 — 뉴스 수집 + 수정 예측  (미국 장 개장 직후)
  21:30  슬롯 3 — 평가 + 발전  (미국 장 마감 후)

주말(토·일)은 건너뜁니다. 서버 재시작 시 오늘 밀린 슬롯을 자동으로 따라잡습니다.
"""
from __future__ import annotations

import threading
import traceback
from datetime import date, datetime, timezone
from typing import Callable

from .config import SETTINGS
from .orchestrator import Orchestrator
from .storage import Storage

# (UTC hour, UTC minute, slot_id)
_SCHEDULE: list[tuple[int, int, int]] = [
    (8, 0, 1),    # 08:00 → 슬롯 1: 기본 예측
    (14, 0, 2),   # 14:00 → 슬롯 2: 뉴스 + 수정 예측
    (21, 30, 3),  # 21:30 → 슬롯 3: 평가 + 발전
]

_SLOT_LABEL = {
    1: "기본 예측 (Phase 1)",
    2: "뉴스 수집 + 수정 예측 (Phase 2+3)",
    3: "평가 + 발전 (Phase 4)",
}

# 다음 체크까지 대기 시간(초). 짧을수록 정확하지만 CPU를 쓴다.
_POLL_SECONDS = 60


def _is_trading_day(d: date) -> bool:
    """월~금을 거래일로 간주. 공휴일은 미처리(향후 확장 가능)."""
    return d.weekday() < 5


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _scheduled_time(day: date, hour: int, minute: int) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, 0,
                    tzinfo=timezone.utc)


class DailyScheduler:
    """백그라운드 스레드로 매일 3개 슬롯을 정해진 UTC 시각에 자동 실행한다."""

    def __init__(self,
                 on_slot_done: Callable[[str, int, dict], None] | None = None):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._on_slot_done = on_slot_done  # 완료 콜백 (웹서버 알림 등)
        self._lock = threading.Lock()  # 중복 실행 방지

    # ------------------------------------------------------------------ #
    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="StockScheduler", daemon=True)
        self._thread.start()
        print("📅 스케줄러 시작 (슬롯 08:00 / 14:00 / 21:30 UTC)")

    def stop(self) -> None:
        self._stop.set()

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------ #
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                today = _utc_now().date()
                if _is_trading_day(today):
                    self._catchup(today)
            except Exception:
                pass  # 루프 사망 방지
            self._stop.wait(timeout=_POLL_SECONDS)

    def _catchup(self, trading_date: date) -> None:
        """오늘 기준으로 시간이 지났으나 아직 안 된 슬롯을 순서대로 실행한다."""
        now = _utc_now()
        date_str = trading_date.isoformat()
        for hour, minute, slot in _SCHEDULE:
            due = _scheduled_time(trading_date, hour, minute)
            if now < due:
                break  # 이후 슬롯들도 아직 시간이 안 됨
            self._run_slot_if_needed(date_str, slot)

    def _run_slot_if_needed(self, cycle_date: str, slot: int) -> None:
        store = Storage(SETTINGS.db_path)
        try:
            if store.slot_done(cycle_date, slot):
                return
        finally:
            store.close()

        with self._lock:
            # 락 획득 후 재확인 (중복 방지)
            store = Storage(SETTINGS.db_path)
            try:
                if store.slot_done(cycle_date, slot):
                    return
                self._execute_slot(store, cycle_date, slot)
            finally:
                store.close()

    def _execute_slot(self, store: Storage, cycle_date: str, slot: int) -> None:
        label = _SLOT_LABEL.get(slot, f"슬롯 {slot}")
        print(f"[스케줄러] {cycle_date} {label} 시작...")
        try:
            orch = Orchestrator(store)
            if slot == 1:
                result = orch.run_phase1_baseline(cycle_date)
            elif slot == 2:
                r2 = orch.run_phase2_news(cycle_date)
                r3 = orch.run_phase3_revised(cycle_date)
                result = {"phase2": r2, "phase3": r3}
            elif slot == 3:
                result = orch.run_phase4_evaluate(cycle_date)
            else:
                return

            store.log_scheduler(cycle_date, slot, "ok",
                                 f"{label} 완료")
            print(f"[스케줄러] {cycle_date} {label} 완료")
            if self._on_slot_done:
                self._on_slot_done(cycle_date, slot, result)

        except Exception as exc:
            detail = traceback.format_exc(limit=5)
            store.log_scheduler(cycle_date, slot, "error", str(exc))
            print(f"[스케줄러] {cycle_date} {label} 오류: {exc}\n{detail}")


# ------------------------------------------------------------------ #
# 스케줄 상태 조회 (웹 API 용)
# ------------------------------------------------------------------ #

def schedule_status(store: Storage) -> dict:
    """오늘 스케줄 현황 + 최근 30개 실행 로그 반환."""
    now = _utc_now()
    today = now.date()
    date_str = today.isoformat()
    is_trading = _is_trading_day(today)

    slots = []
    for hour, minute, slot in _SCHEDULE:
        due = _scheduled_time(today, hour, minute)
        slots.append({
            "slot": slot,
            "label": _SLOT_LABEL[slot],
            "scheduled_utc": f"{hour:02d}:{minute:02d}",
            "due": due.isoformat(),
            "past_due": now >= due,
            "done": store.slot_done(date_str, slot) if is_trading else None,
        })

    return {
        "today": date_str,
        "is_trading_day": is_trading,
        "now_utc": now.strftime("%H:%M"),
        "slots": slots,
        "recent_log": store.scheduler_history(30),
    }

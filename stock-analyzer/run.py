#!/usr/bin/env python3
"""주식 예측 멀티에이전트 시스템 — CLI 진입점.

사용법:
  python run.py serve                  웹 대시보드 실행 (기본 포트 8000)
  python run.py cycle [YYYY-MM-DD]     한 사이클 실행(예측+평가+발전)
  python run.py backtest --days 30     N개 사이클 연속 실행(학습 시뮬레이션)
  python run.py status                 현재 신뢰도/정확도 요약
  python run.py roster                 에이전트 명단 출력
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta

from app.config import SETTINGS
from app.orchestrator import Orchestrator
from app.storage import Storage


def _store() -> Storage:
    return Storage(SETTINGS.db_path)


def cmd_serve(args):
    from app.scheduler import DailyScheduler
    from app.web.server import serve
    if not args.no_scheduler:
        scheduler = DailyScheduler()
        scheduler.start()
    serve(host=args.host, port=args.port)


def cmd_scheduler(args):
    """독립형 스케줄러 (웹서버 없이 백그라운드 실행)."""
    import signal
    import time
    from app.scheduler import DailyScheduler
    scheduler = DailyScheduler()
    scheduler.start()
    # SIGINT/SIGTERM 으로 종료
    def _stop(sig, frame):
        print("\n스케줄러 종료 중...")
        scheduler.stop()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    print("스케줄러 단독 실행 중. Ctrl+C 로 종료하세요.")
    while scheduler.is_running():
        time.sleep(5)


def cmd_cycle(args):
    store = _store()
    orch = Orchestrator(store)
    cycle_date = args.date or date.today().isoformat()
    result = orch.run_full_cycle(cycle_date)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    store.close()


def cmd_backtest(args):
    store = _store()
    orch = Orchestrator(store)
    start = datetime.fromisoformat(args.start).date() if args.start \
        else date.today() - timedelta(days=args.days)
    print(f"백테스트 시작: {start} 부터 {args.days} 사이클\n")
    for i in range(args.days):
        d = (start + timedelta(days=i)).isoformat()
        res = orch.run_full_cycle(d)
        conf = res["confidence"]
        ev = res["evaluation"]
        print(f"[{d}] 앙상블적중 {ev['ensemble_hits']}/{ev['ensemble_total']} "
              f"| 롤링정확도 {conf['rolling_accuracy']:.2f} "
              f"| 보정신뢰도 {conf['calibrated_confidence']:.2f} "
              f"| 실거래가능={conf['trade_ready']}")
    print("\n최종 상태:")
    _print_status(store)
    store.close()


def _print_status(store: Storage):
    conf = store.latest_confidence()
    if not conf:
        print("  데이터 없음. 먼저 cycle/backtest 를 실행하세요.")
        return
    print(f"  학습 사이클 수: {len(store.cycle_dates())}")
    print(f"  전체 정확도:   {conf['overall_accuracy']:.2f}")
    print(f"  롤링 정확도:   {conf['rolling_accuracy']:.2f}")
    print(f"  보정 신뢰도:   {conf['calibrated_confidence']:.2f}")
    print(f"  실거래 가능:   {bool(conf['trade_ready'])}")
    print(f"  판정:          {conf['detail']}")
    print("  예측 에이전트별 적중률:")
    for name in ["momentum", "sentiment", "analyst_consensus",
                 "mean_reversion", "llm_reasoner"]:
        hits, total = store.predictor_accuracy(name)
        acc = f"{hits/total:.2f}" if total else "N/A"
        print(f"    - {name:18s} {acc} ({hits}/{total})")


def cmd_status(args):
    store = _store()
    _print_status(store)
    store.close()


def cmd_roster(args):
    store = _store()
    orch = Orchestrator(store)
    print(json.dumps(orch.agent_roster(), ensure_ascii=False, indent=2))
    store.close()


def main():
    parser = argparse.ArgumentParser(description="주식 예측 멀티에이전트 시스템")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="웹 대시보드 실행")
    p.add_argument("--host", default="0.0.0.0")
    # Render 등 PaaS 는 PORT 환경변수로 포트를 지정한다.
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    p.add_argument("--no-scheduler", action="store_true",
                   help="자동 스케줄러 비활성화 (수동 실행 전용)")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("scheduler", help="자동 스케줄러 단독 실행 (웹서버 없이)")
    p.set_defaults(func=cmd_scheduler)

    p = sub.add_parser("cycle", help="한 사이클 실행")
    p.add_argument("date", nargs="?", default=None)
    p.set_defaults(func=cmd_cycle)

    p = sub.add_parser("backtest", help="여러 사이클 연속 실행")
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--start", default=None)
    p.set_defaults(func=cmd_backtest)

    p = sub.add_parser("status", help="현재 상태 요약")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("roster", help="에이전트 명단")
    p.set_defaults(func=cmd_roster)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

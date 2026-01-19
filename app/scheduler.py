# app/scheduler.py
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import ScheduleItem, ScheduleLog

KST = ZoneInfo("Asia/Seoul")


# -------------------------
# Time helpers (KST naive)
# -------------------------
def now_kst_naive() -> datetime:
    """
    SQLite MVP에서 가장 덜 헷갈리는 방식:
    - "KST 시간"을 DB에 그대로 저장
    - tzinfo는 제거(naive datetime)
    """
    return datetime.now(KST).replace(tzinfo=None)


def truncate_to_minute(dt: datetime) -> datetime:
    # naive datetime 가정
    return dt.replace(second=0, microsecond=0)


# -------------------------
# Lock / logging helpers
# -------------------------
def acquire_minute_lock(db: Session, item_id: int, scheduled_for: datetime) -> bool:
    """
    분 단위 중복 실행 방지:
    (schedule_item_id, scheduled_for) 조합으로 ScheduleLog에 STARTED를 먼저 남겨 선점.

    권장(가능하면): DB에 unique constraint 추가
      Unique(schedule_item_id, scheduled_for)
    """
    existing = (
        db.query(ScheduleLog)
        .filter(
            ScheduleLog.schedule_item_id == item_id,
            ScheduleLog.scheduled_for == scheduled_for,
        )
        .first()
    )
    if existing:
        return False

    log = ScheduleLog(
        schedule_item_id=item_id,
        scheduled_for=scheduled_for,
        ran_at=now_kst_naive(),  # "실제로 시작한 시각" (KST naive)
        status="STARTED",
        error=None,
    )
    db.add(log)
    db.commit()
    return True


def mark_log_success(db: Session, item_id: int, scheduled_for: datetime) -> None:
    log = (
        db.query(ScheduleLog)
        .filter(
            ScheduleLog.schedule_item_id == item_id,
            ScheduleLog.scheduled_for == scheduled_for,
        )
        .order_by(ScheduleLog.id.desc())
        .first()
    )
    if not log:
        return

    log.status = "SUCCESS"
    db.commit()


def mark_log_failed(db: Session, item_id: int, scheduled_for: datetime, err: str) -> None:
    log = (
        db.query(ScheduleLog)
        .filter(
            ScheduleLog.schedule_item_id == item_id,
            ScheduleLog.scheduled_for == scheduled_for,
        )
        .order_by(ScheduleLog.id.desc())
        .first()
    )
    if not log:
        # STARTED 로그가 없으면 최소한 실패 로그라도 남김
        log = ScheduleLog(
            schedule_item_id=item_id,
            scheduled_for=scheduled_for,
            ran_at=now_kst_naive(),
            status="FAILED",
            error=err,
        )
        db.add(log)
        db.commit()
        return

    log.status = "FAILED"
    log.error = err
    db.commit()


# -------------------------
# Due check / runner
# -------------------------
def is_due_this_minute(item: ScheduleItem, scheduled_for: datetime) -> bool:
    """
    TODO: 프로젝트 규칙에 맞게 구현해야 하는 핵심 판별 함수.

    예) item.time_of_day == "22:55" 형태라면:
      scheduled_for.strftime("%H:%M") == item.time_of_day 인지 비교

    현재는 안전을 위해 "time_of_day"가 있으면 그거만 맞을 때 실행하도록 예시 구현.
    (원하는 스펙에 맞게 바꿔줘)
    """
    if getattr(item, "time_of_day", None):
        return scheduled_for.strftime("%H:%M") == item.time_of_day
    return True


def run_one_item(db: Session, item: ScheduleItem, scheduled_for: datetime) -> None:
    """
    실제 작업 실행 부분.
    예: 알림 생성/전화/문자 큐잉/오케스트레이터 트리거 등

    MVP에서는 일단 로그만 남기고 끝내도 됨.
    """
    # 예시로 콘솔 출력
    print(
        "[scheduler] RUN",
        f"item_id={item.id}",
        f"title={getattr(item, 'title', None)}",
        f"scheduled_for={scheduled_for.isoformat()}",
    )
    # 실패 테스트:
    # raise RuntimeError("test failure")


# -------------------------
# Main loop
# -------------------------
async def scheduler_loop(poll_seconds: float = 1.0) -> None:
    """
    - 매 초 tick
    - "이번 분"(KST naive, 분 단위 절삭)을 기준으로 due items 실행
    - 중복 실행 방지: scheduled_for 기준으로 STARTED 로그 선점
    """
    print("[scheduler] started", "server_now_kst_naive=", now_kst_naive().isoformat())

    while True:
        try:
            tick = now_kst_naive()
            scheduled_for = truncate_to_minute(tick)

            db = SessionLocal()
            try:
                due_items = (
                    db.query(ScheduleItem)
                    .filter(ScheduleItem.enabled == True)  # noqa: E712
                    .all()
                )

                for item in due_items:
                    if not is_due_this_minute(item, scheduled_for):
                        continue

                    locked = acquire_minute_lock(db, item.id, scheduled_for)
                    if not locked:
                        continue

                    try:
                        run_one_item(db, item, scheduled_for)
                        mark_log_success(db, item.id, scheduled_for)
                    except Exception as e:
                        mark_log_failed(db, item.id, scheduled_for, str(e))

            finally:
                db.close()

        except Exception as outer:
            # scheduler 자체가 죽지 않도록 보호
            print("[scheduler] outer error:", repr(outer))

        await asyncio.sleep(poll_seconds)


# -------------------------
# Background task controls
# -------------------------
_scheduler_task: Optional[asyncio.Task] = None


def start_scheduler() -> None:
    """
    FastAPI startup에서 호출.
    주의: 반드시 "실행 중인 event loop"가 있어야 함(uvicorn 환경 OK).
    """
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return

    loop = asyncio.get_running_loop()
    _scheduler_task = loop.create_task(scheduler_loop())
    print("[scheduler] task created")


def stop_scheduler() -> None:
    """
    FastAPI shutdown에서 호출.
    """
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        print("[scheduler] task cancelled")
    _scheduler_task = None

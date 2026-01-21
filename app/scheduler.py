# app/scheduler.py
from __future__ import annotations

import asyncio
import traceback
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional, List

from sqlalchemy import and_
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import ScheduleItem, ScheduleLog
from .tts_queue import enqueue_tts

POLL_INTERVAL_SECONDS = 1
DUE_WINDOW_SECONDS = 60  # 1초는 놓치기 쉬움. 로그 중복방지 있으니 60초 권장.

_scheduler_task: Optional[asyncio.Task] = None


@dataclass(frozen=True)
class DueDecision:
    is_due: bool
    scheduled_for: Optional[datetime] = None


def _now_local() -> datetime:
    return datetime.now()


def _parse_time_of_day(value) -> Optional[time]:
    """
    DB에는 "HH:MM" 문자열로 저장한다고 가정.
    """
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        s = value.strip()
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                return datetime.strptime(s, fmt).time()
            except ValueError:
                pass
    return None


def _is_enabled(item: ScheduleItem) -> bool:
    # enabled 우선. (과거 필드 is_active도 호환 가능)
    if hasattr(item, "enabled"):
        return bool(getattr(item, "enabled"))
    if hasattr(item, "is_active"):
        return bool(getattr(item, "is_active"))
    return True


def _compute_scheduled_for(item: ScheduleItem, now: datetime) -> Optional[datetime]:
    if not _is_enabled(item):
        return None

    tod = _parse_time_of_day(getattr(item, "time_of_day", None))
    if tod is None:
        return None

    return datetime.combine(now.date(), tod)


def _is_due_now(item: ScheduleItem, now: datetime, window_seconds: int) -> DueDecision:
    scheduled_for = _compute_scheduled_for(item, now)
    if scheduled_for is None:
        return DueDecision(False, None)

    if scheduled_for <= now < (scheduled_for + timedelta(seconds=window_seconds)):
        return DueDecision(True, scheduled_for)

    return DueDecision(False, scheduled_for)


def _already_logged(db: Session, item_id: int, scheduled_for: datetime) -> bool:
    existing = (
        db.query(ScheduleLog)
        .filter(
            and_(
                ScheduleLog.item_id == item_id,
                ScheduleLog.scheduled_for == scheduled_for,
            )
        )
        .first()
    )
    return existing is not None


def _log_run(
    db: Session,
    item_id: int,
    scheduled_for: datetime,
    status: str,
    error: Optional[str] = None,
) -> None:
    log = ScheduleLog(
        item_id=item_id,
        scheduled_for=scheduled_for,
        status=status,
        error=error,
        created_at=_now_local(),
    )
    db.add(log)
    db.commit()


async def _run_item_tts(item: ScheduleItem) -> None:
    title = (getattr(item, "title", None) or "").strip()
    body = (getattr(item, "message", None) or "").strip()

    if title and body:
        msg = f"{title}. {body}"
    elif body:
        msg = body
    elif title:
        msg = title
    else:
        msg = "알림입니다."

    await enqueue_tts(msg)


async def scheduler_loop() -> None:
    try:
        print("[scheduler] loop started")
        while True:
            now = _now_local()
            # tick 로그는 너무 많으면 주석 처리 가능
            # print("[scheduler] tick", now.strftime("%H:%M:%S"))

            db: Session = SessionLocal()
            try:
                items: List[ScheduleItem] = db.query(ScheduleItem).all()

                for item in items:
                    # ORM 객체 자체를 print하지 말 것(재귀/대량 출력 가능)
                    decision = _is_due_now(item, now, window_seconds=DUE_WINDOW_SECONDS)
                    if not decision.is_due or decision.scheduled_for is None:
                        continue

                    if _already_logged(db, item.id, decision.scheduled_for):
                        continue

                    try:
                        await _run_item_tts(item)
                        _log_run(db, item.id, decision.scheduled_for, "SUCCESS", None)
                        print(
                            "[scheduler] SUCCESS",
                            f"item_id={item.id}",
                            f"scheduled_for={decision.scheduled_for.isoformat(sep=' ', timespec='seconds')}",
                        )
                    except Exception as e:
                        _log_run(db, item.id, decision.scheduled_for, "FAILED", repr(e))
                        print(
                            "[scheduler] FAILED",
                            f"item_id={item.id}",
                            f"scheduled_for={decision.scheduled_for.isoformat(sep=' ', timespec='seconds')}",
                            f"error={repr(e)}",
                        )

            finally:
                db.close()

            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    except asyncio.CancelledError:
        print("[scheduler] task cancelled")
        raise
    except Exception as e:
        print("[scheduler] task crashed:", repr(e))
        traceback.print_exc()
        raise


def start_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        return

    loop = asyncio.get_running_loop()
    _scheduler_task = loop.create_task(scheduler_loop())
    print("[scheduler] started")


async def stop_scheduler() -> None:
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    _scheduler_task = None
    print("[scheduler] stopped")

# app/scheduler.py
from __future__ import annotations

import traceback
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import and_
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import ScheduleItem, ScheduleLog
from .tts_queue import enqueue_tts

scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


@dataclass(frozen=True)
class DueDecision:
    is_due: bool
    scheduled_for: Optional[datetime] = None


def _now_local() -> datetime:
    return datetime.now()


def parse_time_of_day(value) -> Optional[time]:
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
    if hasattr(item, "enabled"):
        return bool(getattr(item, "enabled"))
    if hasattr(item, "is_active"):
        return bool(getattr(item, "is_active"))
    return True


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


async def run_item_job(item_id: int) -> None:
    db: Session = SessionLocal()
    now = _now_local()
    try:
        item: ScheduleItem | None = db.get(ScheduleItem, item_id)
        if not item:
            return
        if not _is_enabled(item):
            return

        tod = parse_time_of_day(getattr(item, "time_of_day", None))
        if tod is None:
            return

        scheduled_for = datetime.combine(now.date(), tod)

        if _already_logged(db, item.id, scheduled_for):
            return

        try:
            await _run_item_tts(item)
            _log_run(db, item.id, scheduled_for, "SUCCESS", None)
            print("[scheduler] SUCCESS", f"item_id={item.id}", f"scheduled_for={scheduled_for}")
        except Exception as e:
            _log_run(db, item.id, scheduled_for, "FAILED", repr(e))
            print("[scheduler] FAILED", f"item_id={item.id}", f"scheduled_for={scheduled_for}", f"error={repr(e)}")
            traceback.print_exc()

    finally:
        db.close()


def upsert_item_job(item: ScheduleItem) -> None:
    job_id = f"item:{item.id}"

    if not _is_enabled(item):
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        return

    tod = parse_time_of_day(getattr(item, "time_of_day", None))
    if tod is None:
        # 시간이 없으면 job 제거
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        return

    trigger = CronTrigger(hour=tod.hour, minute=tod.minute, second=tod.second)

    scheduler.add_job(
        run_item_job,
        trigger=trigger,
        args=[item.id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=60 * 10,  # 10분: 서버 잠깐 멈춤/이벤트 루프 지연 허용
        coalesce=True,
        max_instances=1,
    )

def remove_item_job(item_id: int) -> None:
    try:
        scheduler.remove_job(f"item:{item_id}")
    except Exception:
        pass


def rehydrate_jobs_from_db() -> None:
    db: Session = SessionLocal()
    try:
        items: List[ScheduleItem] = db.query(ScheduleItem).all()
        for item in items:
            upsert_item_job(item)
        print(f"[scheduler] rehydrated {len(items)} items")
    finally:
        db.close()


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.start()
    rehydrate_jobs_from_db()
    print("[scheduler] started")


async def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
    print("[scheduler] stopped")

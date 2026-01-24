# app/main.py
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .scheduler import (
    start_scheduler,
    stop_scheduler,
    upsert_item_job,
    remove_item_job,
    parse_time_of_day,
)
from .db import Base, engine, DB_PATH, get_db
from . import models
from .tts_queue import (
    start_tts_worker,
    enqueue_tts,
    queue_size,
    last_error,
    last_spoken_at,
    spoken_count,
)

app = FastAPI(title="AI Guardian Eye - Scheduling MVP", version="0.1.0")


# ---------- Schemas ----------
class ScheduleItemCreate(BaseModel):
    user_id: Optional[int] = None
    title: str
    message: str
    time_of_day: str = Field(..., description="HH:MM or HH:MM:SS")
    enabled: bool = True


class ScheduleItemOut(BaseModel):
    id: int
    user_id: Optional[int]
    title: str
    message: str
    time_of_day: str
    enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScheduleItemUpdate(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    time_of_day: Optional[str] = None
    enabled: Optional[bool] = None


class ScheduleLogOut(BaseModel):
    id: int
    item_id: int
    scheduled_for: datetime
    status: str
    error: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SpeakReq(BaseModel):
    text: str


# ---------- Routes ----------
@app.get("/now")
def now():
    return {
        "datetime_now": datetime.now().isoformat(),
        "time_tzname": time.tzname,
    }


@app.on_event("startup")
async def on_startup():
    print("DB_PATH =", DB_PATH)
    Base.metadata.create_all(bind=engine)

    start_tts_worker()
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown():
    await stop_scheduler()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/schedule-items", response_model=ScheduleItemOut)
def create_schedule_item(
    payload: ScheduleItemCreate,
    db: Session = Depends(get_db),
):
    if parse_time_of_day(payload.time_of_day) is None:
        raise HTTPException(
            status_code=400,
            detail="time_of_day must be 'HH:MM' or 'HH:MM:SS'",
        )

    item = models.ScheduleItem(
        user_id=payload.user_id,
        title=payload.title,
        message=payload.message,
        time_of_day=payload.time_of_day,
        enabled=payload.enabled,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    upsert_item_job(item)
    return item


@app.get("/schedule-items", response_model=List[ScheduleItemOut])
def list_schedule_items(db: Session = Depends(get_db)):
    return (
        db.query(models.ScheduleItem)
        .order_by(models.ScheduleItem.id.desc())
        .all()
    )


@app.get("/schedule-logs", response_model=List[ScheduleLogOut])
def recent_logs(limit: int = 20, db: Session = Depends(get_db)):
    return (
        db.query(models.ScheduleLog)
        .order_by(models.ScheduleLog.id.desc())
        .limit(limit)
        .all()
    )


@app.post("/debug/speak")
async def debug_speak(req: SpeakReq):
    try:
        await enqueue_tts(req.text)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))


@app.post("/debug/tts")
async def debug_tts(payload: dict = Body(...)):
    title = (payload.get("title") or "").strip()
    message = (payload.get("message") or payload.get("text") or "").strip()

    if title and message:
        msg = f"{title}. {message}"
    else:
        msg = message or title or "알림입니다."

    await enqueue_tts(msg)
    return {"ok": True, "enqueued_text": msg}


@app.get("/debug/tts-status")
def tts_status():
    return {
        "queue_size": queue_size(),
        "spoken_count": spoken_count,
        "last_spoken_at": last_spoken_at,
        "last_error": last_error,
    }


@app.patch("/schedule-items/{item_id}", response_model=ScheduleItemOut)
def update_schedule_item(
    item_id: int,
    payload: ScheduleItemUpdate,
    db: Session = Depends(get_db),
):
    item = db.get(models.ScheduleItem, item_id)
    if not item:
        raise HTTPException(404, "not found")

    if payload.title is not None:
        item.title = payload.title
    if payload.message is not None:
        item.message = payload.message
    if payload.time_of_day is not None:
        if parse_time_of_day(payload.time_of_day) is None:
            raise HTTPException(
                status_code=400,
                detail="time_of_day must be 'HH:MM' or 'HH:MM:SS'",
            )
        item.time_of_day = payload.time_of_day
    if payload.enabled is not None:
        item.enabled = payload.enabled

    db.commit()
    db.refresh(item)

    upsert_item_job(item)
    return item


@app.delete("/schedule-items/{item_id}")
def delete_schedule_item(item_id: int, db: Session = Depends(get_db)):
    item = db.get(models.ScheduleItem, item_id)
    if not item:
        raise HTTPException(404, "not found")

    remove_item_job(item_id)

    db.delete(item)
    db.commit()
    return {"ok": True}


print("LOADED FILE:", __file__)

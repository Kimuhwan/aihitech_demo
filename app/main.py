# app/main.py
from __future__ import annotations

import time
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .db import Base, engine, DB_PATH, get_db
from . import models  # 모델 로드(중요)
from .scheduler import start_scheduler, stop_scheduler
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
    # 어떤 DB 파일을 쓰는지 확인
    print("DB_PATH =", DB_PATH)

    # 테이블 생성 (models가 import되어 있어야 실제 테이블이 생김)
    Base.metadata.create_all(bind=engine)

    # TTS 큐 워커 시작 (선택: TTS 쓰면 켜기)
    start_tts_worker()

    # 스케줄러 시작 (너 프로젝트에서 쓰는 경우)
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
    # 간단 검증(원하면 더 엄격히)
    if not payload.time_of_day or ":" not in payload.time_of_day:
        raise HTTPException(status_code=400, detail="time_of_day must be like 'HH:MM'")

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
    rows = (
        db.query(models.ScheduleLog)
        .order_by(models.ScheduleLog.id.desc())
        .limit(limit)
        .all()
    )
    return rows


@app.post("/debug/speak")
async def debug_speak(req: SpeakReq):
    try:
        await enqueue_tts(req.text)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=repr(e))

@app.get("/debug/tts")
def debug_tts():
    return {
        "queue_size": queue_size(),
        "spoken_count": spoken_count,
        "last_spoken_at": last_spoken_at,
        "last_error": last_error,
    }


print("LOADED FILE:", __file__)

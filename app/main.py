# app/main.py
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from datetime import datetime
import time
from .db import Base, engine, get_db
from . import models
from .scheduler import start_scheduler, stop_scheduler

app = FastAPI(title="AI Guardian Eye - Scheduling MVP", version="0.1.0")


@app.get("/now")
def now():
    return {
        "datetime_now": datetime.now().isoformat(),
        "time_tzname": time.tzname,
    }


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)  # 데모용
    start_scheduler()

@app.on_event("shutdown")
def on_shutdown():
    stop_scheduler()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/schedule-items")
def create_schedule_item(payload: dict, db: Session = Depends(get_db)):
    # payload 예: {"title":"복약","message":"약 드실 시간입니다","time_of_day":"22:55","enabled":true}
    item = models.ScheduleItem(
        user_id=payload.get("user_id"),
        title=payload["title"],
        message=payload["message"],
        time_of_day=payload["time_of_day"],
        enabled=payload.get("enabled", True),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

@app.get("/schedule-logs")
def recent_logs(limit: int = 20, db: Session = Depends(get_db)):
    rows = (
        db.query(models.ScheduleLog)
        .order_by(models.ScheduleLog.id.desc())
        .limit(limit)
        .all()
    )
    return rows

print("LOADED FILE:", __file__)


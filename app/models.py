# models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from .db import Base  # 네 프로젝트 Base import 경로에 맞춰 조정

class ScheduleItem(Base):
    __tablename__ = "schedule_items"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=True)

    title = Column(String(100), nullable=False)
    message = Column(String(500), nullable=False)
    time_of_day = Column(String(5), nullable=False)  # "HH:MM"

    enabled = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)

    logs = relationship("ScheduleLog", back_populates="item", cascade="all, delete-orphan")


class ScheduleLog(Base):
    __tablename__ = "schedule_logs"

    id = Column(Integer, primary_key=True, index=True)

    schedule_item_id = Column(Integer, ForeignKey("schedule_items.id", ondelete="CASCADE"), nullable=False, index=True)

    ran_at = Column(DateTime(timezone=False), nullable=False)
    scheduled_for = Column(DateTime(timezone=False), nullable=False)
    status = Column(String(20), nullable=False)  # "STARTED" | "SUCCESS" | "FAILED"
    error = Column(Text, nullable=True)

    item = relationship("ScheduleItem", back_populates="logs")

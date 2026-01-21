# app/models.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class ScheduleItem(Base):
    __tablename__ = "schedule_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # "HH:MM" 또는 "HH:MM:SS" 문자열로 저장 (SQLite/간단 MVP용)
    time_of_day: Mapped[str] = mapped_column(String(8), nullable=False)

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    logs: Mapped[list["ScheduleLog"]] = relationship(
        "ScheduleLog",
        back_populates="item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        # relationship/logs 출력 금지(재귀/대량출력 방지)
        return f"ScheduleItem(id={self.id}, title={self.title!r}, time_of_day={self.time_of_day!r}, enabled={self.enabled})"


class ScheduleLog(Base):
    __tablename__ = "schedule_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("schedule_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    scheduled_for: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False)  # "SUCCESS" | "FAILED"
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    item: Mapped["ScheduleItem"] = relationship("ScheduleItem", back_populates="logs")

    __table_args__ = (
        # 같은 item + 같은 scheduled_for는 1번만 기록되게 (중복 실행 방지)
        UniqueConstraint("item_id", "scheduled_for", name="uq_schedulelog_item_scheduledfor"),
        Index("ix_schedule_logs_item_scheduled_for", "item_id", "scheduled_for"),
    )

    def __repr__(self) -> str:
        return f"ScheduleLog(id={self.id}, item_id={self.item_id}, scheduled_for={self.scheduled_for}, status={self.status!r})"

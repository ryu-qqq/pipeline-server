from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.adapter.outbound.mysql.database import Base


class SelectionEntity(Base):
    __tablename__ = "selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    temperature_celsius: Mapped[float] = mapped_column(Float, nullable=False)
    wiper_active: Mapped[bool] = mapped_column(nullable=False)
    wiper_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    headlights_on: Mapped[bool] = mapped_column(nullable=False)
    source_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OddTagEntity(Base):
    __tablename__ = "odd_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    video_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    weather: Mapped[str] = mapped_column(String(20), nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(20), nullable=False)
    road_surface: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_odd_tags_task_video", "task_id", "video_id", unique=True),
        Index("ix_odd_tags_search", "task_id", "video_id", "weather", "time_of_day", "road_surface"),
    )


class LabelEntity(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    video_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    object_class: Mapped[str] = mapped_column(String(30), nullable=False)
    obj_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    labeled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_labels_task_video_class", "task_id", "video_id", "object_class", unique=True),
        Index("ix_labels_search", "task_id", "object_class", "obj_count", "avg_confidence"),
    )


class RejectionEntity(Base):
    __tablename__ = "rejections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_rejections_task_stage_reason", "task_id", "stage", "reason"),
        Index("ix_rejections_source", "task_id", "source_id"),
    )

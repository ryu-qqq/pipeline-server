from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.adapter.outbound.mysql.database import Base


class SelectionEntity(Base):
    __tablename__ = "selections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
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
    video_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    weather: Mapped[str] = mapped_column(String(20), nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(20), nullable=False)
    road_surface: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LabelEntity(Base):
    __tablename__ = "labels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    object_class: Mapped[str] = mapped_column(String(30), nullable=False)
    obj_count: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    labeled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_labels_video_class", "video_id", "object_class", unique=True),)


class RejectionEntity(Base):
    __tablename__ = "rejections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_identifier: Mapped[str] = mapped_column(String(200), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    raw_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

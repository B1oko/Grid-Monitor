from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Inverter(Base):
    __tablename__ = "inverters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    driver_id: Mapped[str] = mapped_column(String(64), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=502)
    unit_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    poll_interval_s: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    battery_capacity_kwh: Mapped[float | None] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    samples: Mapped[list[InverterSample]] = relationship(
        back_populates="inverter", cascade="all, delete-orphan"
    )


class InverterSample(Base):
    __tablename__ = "inverter_samples"
    __table_args__ = (UniqueConstraint("inverter_id", "ts", name="uq_inverter_sample_ts"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inverter_id: Mapped[int] = mapped_column(
        ForeignKey("inverters.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    pv_power_w: Mapped[int | None] = mapped_column(Integer)
    battery_power_w: Mapped[int | None] = mapped_column(Integer)
    grid_power_w: Mapped[int | None] = mapped_column(Integer)
    load_power_w: Mapped[int | None] = mapped_column(Integer)
    inverter_power_w: Mapped[int | None] = mapped_column(Integer)
    battery_soc_pct: Mapped[float | None] = mapped_column(Float)
    battery_temp_c: Mapped[float | None] = mapped_column(Float)

    inverter: Mapped[Inverter] = relationship(back_populates="samples")


class AppSetting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)

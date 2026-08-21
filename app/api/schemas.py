from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class InverterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    driver_id: str = Field(min_length=1, max_length=64)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=502, ge=1, le=65535)
    unit_id: int = Field(default=1, ge=1, le=255)
    timeout_seconds: float = Field(default=3.0, ge=0.5, le=30)
    poll_interval_s: float = Field(default=2.0, ge=0.5, le=60)
    battery_capacity_kwh: float | None = Field(default=None, ge=0)
    enabled: bool = True
    extra: dict[str, Any] | None = None


class InverterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    driver_id: str | None = Field(default=None, min_length=1, max_length=64)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    unit_id: int | None = Field(default=None, ge=1, le=255)
    timeout_seconds: float | None = Field(default=None, ge=0.5, le=30)
    poll_interval_s: float | None = Field(default=None, ge=0.5, le=60)
    battery_capacity_kwh: float | None = Field(default=None, ge=0)
    enabled: bool | None = None
    extra: dict[str, Any] | None = None


class InverterOut(BaseModel):
    id: int
    name: str
    driver_id: str
    host: str
    port: int
    unit_id: int
    timeout_seconds: float
    poll_interval_s: float
    battery_capacity_kwh: float | None
    enabled: bool
    extra: dict[str, Any] | None

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    timezone: str | None = None
    retention_days: int | None = Field(default=None, ge=0, le=3650)
    downsample_after_days: int | None = Field(default=None, ge=0, le=3650)
    recorder_interval_seconds: float | None = Field(default=None, ge=10, le=3600)
    discovery_concurrency: int | None = Field(default=None, ge=1, le=256)
    discovery_port_scan_timeout: float | None = Field(default=None, ge=0.1, le=5)
    discovery_probe_timeout: float | None = Field(default=None, ge=0.2, le=10)
    discovery_subnet_prefix_length: int | None = Field(default=None, ge=16, le=30)


class Resolution(StrEnum):
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


class HistoryPoint(BaseModel):
    ts: datetime | str
    pv_power_w: int | None = None
    battery_power_w: int | None = None
    grid_power_w: int | None = None
    load_power_w: int | None = None
    inverter_power_w: int | None = None
    battery_soc_pct: float | None = None
    battery_temp_c: float | None = None

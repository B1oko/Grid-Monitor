from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AppSetting

DEFAULT_SETTINGS: dict[str, Any] = {
    "timezone": "UTC",
    "retention_days": 365,
    "downsample_after_days": 30,
    "recorder_interval_seconds": 300.0,
    "discovery_concurrency": 32,
    "discovery_port_scan_timeout": 0.5,
    "discovery_probe_timeout": 2.0,
    "discovery_subnet_prefix_length": 24,
    "latitude": None,
    "longitude": None,
    "alerts_check_interval_seconds": 10.0,
    "alert_overload_enabled": True,
    "alert_overload_limit_w": 5500,
    "alert_overload_minutes": 1.0,
    "alert_no_pv_enabled": True,
    "alert_no_pv_minutes": 30.0,
    "alert_no_pv_threshold_w": 50,
    "alert_no_pv_min_sun_elevation_deg": 15.0,
    "alert_offline_enabled": True,
    "alert_offline_minutes": 10.0,
}


class SettingsStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_all(self) -> dict[str, Any]:
        merged = dict(DEFAULT_SETTINGS)
        async with self._session_factory() as session:
            rows = (await session.execute(select(AppSetting))).scalars().all()
        for row in rows:
            merged[row.key] = row.value
        return merged

    async def get(self, key: str, default: Any = None) -> Any:
        settings = await self.get_all()
        return settings.get(key, default)

    async def update(self, values: dict[str, Any]) -> dict[str, Any]:
        unknown = set(values) - set(DEFAULT_SETTINGS)
        if unknown:
            raise ValueError(f"Unknown setting keys: {sorted(unknown)}")

        async with self._session_factory() as session:
            for key, value in values.items():
                row = await session.get(AppSetting, key)
                if row is None:
                    session.add(AppSetting(key=key, value=value))
                else:
                    row.value = value
            await session.commit()
        return await self.get_all()

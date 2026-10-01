from __future__ import annotations

import asyncio
import logging
from datetime import UTC

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import InverterSample
from app.drivers.base import InverterReading
from app.services.live_manager import Readable

logger = logging.getLogger(__name__)


class Recorder:
    """Writes one sample per interval, independent of live WebSocket clients."""

    def __init__(
        self,
        *,
        inverter_id: int,
        driver: Readable,
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: float,
    ) -> None:
        self._inverter_id = inverter_id
        self._driver = driver
        self._session_factory = session_factory
        self._interval = interval_seconds
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name=f"recorder-{self._inverter_id}")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        try:
            while True:
                await self._record_sample()
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise

    async def _record_sample(self) -> None:
        try:
            reading = await self._driver.read()
        except Exception as exc:
            logger.warning("Recorder[%s]: could not read inverter: %s", self._inverter_id, exc)
            return

        await self.store_reading(reading)

    async def store_reading(self, reading: InverterReading) -> None:
        sample = InverterSample(
            inverter_id=self._inverter_id,
            ts=reading.timestamp
            if reading.timestamp.tzinfo
            else reading.timestamp.replace(tzinfo=UTC),
            pv_power_w=reading.pv_power_w,
            battery_power_w=reading.battery_power_w,
            grid_power_w=reading.grid_power_w,
            load_power_w=reading.load_power_w,
            inverter_power_w=reading.inverter_power_w,
            battery_soc_pct=reading.battery_soc_pct,
            battery_temp_c=reading.battery_temp_c,
        )
        try:
            async with self._session_factory() as session:
                session.add(sample)
                await session.commit()
        except Exception as exc:
            logger.error("Recorder[%s]: could not write to database: %s", self._inverter_id, exc)

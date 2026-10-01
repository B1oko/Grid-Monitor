from __future__ import annotations

import time

from app.drivers.base import InverterDriver, InverterReading


class SharedReader:
    """Single entry point to an inverter driver for the recorder, live poller and alerts.

    All consumers share one driver (and so one Modbus connection). The latest successful
    reading is cached so the alert monitor can reuse live samples instead of polling again.
    """

    def __init__(self, driver: InverterDriver) -> None:
        self._driver = driver
        self._last_reading: InverterReading | None = None
        self._last_read_at: float | None = None

    @property
    def driver(self) -> InverterDriver:
        return self._driver

    async def read(self) -> InverterReading:
        reading = await self._driver.read()
        self._last_reading = reading
        self._last_read_at = time.monotonic()
        return reading

    async def read_recent(self, max_age_seconds: float) -> InverterReading:
        if (
            self._last_reading is not None
            and self._last_read_at is not None
            and time.monotonic() - self._last_read_at <= max_age_seconds
        ):
            return self._last_reading
        return await self.read()

    async def close(self) -> None:
        await self._driver.close()

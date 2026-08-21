from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Inverter, InverterSample
from app.db.timebucket import time_bucket

logger = logging.getLogger(__name__)


class RetentionService:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], dialect_name: str
    ) -> None:
        self._session_factory = session_factory
        self._dialect_name = dialect_name

    async def run(self, *, retention_days: int, downsample_after_days: int) -> None:
        if downsample_after_days > 0:
            await self._downsample(downsample_after_days)
        if retention_days > 0:
            await self._purge(retention_days)

    async def _purge(self, retention_days: int) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        async with self._session_factory() as session:
            result = await session.execute(delete(InverterSample).where(InverterSample.ts < cutoff))
            await session.commit()
            logger.info(
                "Retention: deleted %s samples older than %s days", result.rowcount, retention_days
            )

    async def _downsample(self, downsample_after_days: int) -> None:
        cutoff = datetime.now(UTC) - timedelta(days=downsample_after_days)
        async with self._session_factory() as session:
            dialect = self._dialect_name
            inverter_ids = (await session.execute(select(Inverter.id))).scalars().all()

            for inverter_id in inverter_ids:
                bucket = time_bucket(InverterSample.ts, "hour", dialect)
                rows = (
                    await session.execute(
                        select(
                            bucket.label("ts"),
                            func.round(func.avg(InverterSample.pv_power_w)).label("pv_power_w"),
                            func.round(func.avg(InverterSample.battery_power_w)).label(
                                "battery_power_w"
                            ),
                            func.round(func.avg(InverterSample.grid_power_w)).label("grid_power_w"),
                            func.round(func.avg(InverterSample.load_power_w)).label("load_power_w"),
                            func.round(func.avg(InverterSample.inverter_power_w)).label(
                                "inverter_power_w"
                            ),
                            func.round(func.avg(InverterSample.battery_soc_pct), 2).label(
                                "battery_soc_pct"
                            ),
                            func.round(func.avg(InverterSample.battery_temp_c), 1).label(
                                "battery_temp_c"
                            ),
                        )
                        .where(
                            InverterSample.inverter_id == inverter_id,
                            InverterSample.ts < cutoff,
                        )
                        .group_by(bucket)
                    )
                ).all()

                await session.execute(
                    delete(InverterSample).where(
                        InverterSample.inverter_id == inverter_id,
                        InverterSample.ts < cutoff,
                    )
                )

                for row in rows:
                    ts = row.ts
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts.replace(" ", "T")).replace(tzinfo=UTC)
                    elif isinstance(ts, datetime) and ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    session.add(
                        InverterSample(
                            inverter_id=inverter_id,
                            ts=ts,
                            pv_power_w=int(row.pv_power_w) if row.pv_power_w is not None else None,
                            battery_power_w=(
                                int(row.battery_power_w)
                                if row.battery_power_w is not None
                                else None
                            ),
                            grid_power_w=int(row.grid_power_w)
                            if row.grid_power_w is not None
                            else None,
                            load_power_w=int(row.load_power_w)
                            if row.load_power_w is not None
                            else None,
                            inverter_power_w=(
                                int(row.inverter_power_w)
                                if row.inverter_power_w is not None
                                else None
                            ),
                            battery_soc_pct=(
                                float(row.battery_soc_pct)
                                if row.battery_soc_pct is not None
                                else None
                            ),
                            battery_temp_c=(
                                float(row.battery_temp_c)
                                if row.battery_temp_c is not None
                                else None
                            ),
                        )
                    )
            await session.commit()
            logger.info("Retention: downsampled samples older than %s days", downsample_after_days)

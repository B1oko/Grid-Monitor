"""Energy totals (kWh) per local day or month, computed from stored power samples.

Samples are averaged per UTC hour in SQL, splitting signed flows into their two
directions first so that, for example, grid import and export do not cancel out.
Each hour then contributes ``average power x time covered`` and is assigned to a
day or month in the viewer's time zone.

Samples older than the downsampling threshold are already hourly averages of the
signed value, so for those hours import/export (and charge/discharge) within the
same hour net out. This only matters for the year view and is usually small.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InverterSample
from app.db.timebucket import parse_bucket_ts, time_bucket

EnergyResolution = Literal["day", "month"]

# Output field -> (sample column, direction). +1 keeps positive values, -1 keeps
# the magnitude of negative values. Signs follow InverterReading: grid > 0 is
# import, battery > 0 is discharge.
FLOWS: dict[str, tuple[str, int]] = {
    "solar_kwh": ("pv_power_w", 1),
    "home_kwh": ("load_power_w", 1),
    "grid_import_kwh": ("grid_power_w", 1),
    "grid_export_kwh": ("grid_power_w", -1),
    "battery_charge_kwh": ("battery_power_w", -1),
    "battery_discharge_kwh": ("battery_power_w", 1),
}

HOUR = timedelta(hours=1)


def _directional_avg(column_name: str, sign: int):
    column = getattr(InverterSample, column_name)
    kept = column if sign > 0 else -column
    # NULL samples stay NULL so they are ignored by AVG.
    return func.avg(case((column.is_(None), None), (kept > 0, kept), else_=0))


def _period_start(local: datetime, resolution: EnergyResolution) -> datetime:
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.replace(day=1) if resolution == "month" else start


async def energy_totals(
    session: AsyncSession,
    *,
    dialect: str,
    inverter_id: int,
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
    resolution: EnergyResolution,
    now: datetime | None = None,
) -> list[dict]:
    start, end = (value if value.tzinfo else value.replace(tzinfo=UTC) for value in (start, end))
    end = min(end, now or datetime.now(UTC))
    bucket = time_bucket(InverterSample.ts, "hour", dialect).label("ts")
    stmt = (
        select(
            bucket,
            *(_directional_avg(col, sign).label(key) for key, (col, sign) in FLOWS.items()),
        )
        .where(
            InverterSample.inverter_id == inverter_id,
            InverterSample.ts >= start,
            InverterSample.ts <= end,
        )
        .group_by(bucket)
    )
    rows = (await session.execute(stmt)).all()

    totals: dict[datetime, dict[str, float | None]] = defaultdict(lambda: dict.fromkeys(FLOWS))
    for row in rows:
        hour_start = parse_bucket_ts(row.ts)
        covered = min(hour_start + HOUR, end) - max(hour_start, start)
        hours = max(covered, timedelta(0)) / HOUR
        period = _period_start(hour_start.astimezone(tz), resolution)
        for key in FLOWS:
            avg_w = getattr(row, key)
            if avg_w is None:
                continue
            totals[period][key] = (totals[period][key] or 0.0) + float(avg_w) * hours / 1000

    return [
        {
            "ts": period.isoformat(),
            **{key: None if value is None else round(value, 3) for key, value in values.items()},
        }
        for period, values in sorted(totals.items())
    ]

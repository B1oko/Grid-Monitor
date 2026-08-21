from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import AppState, get_state
from app.api.schemas import Resolution
from app.db.models import InverterSample
from app.db.timebucket import serialize_bucket_ts, time_bucket

router = APIRouter(prefix="/api", tags=["history"])


def _maybe_int(value: object) -> int | None:
    return int(value) if value is not None else None


def _maybe_float(value: object) -> float | None:
    return float(value) if value is not None else None


@router.get("/history")
async def get_history(
    inverter_id: Annotated[int, Query()],
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
    state: AppState = Depends(get_state),
    resolution: Annotated[Resolution, Query()] = Resolution.HOUR,
) -> list[dict]:
    async with state.session_factory() as session:
        dialect = state.engine.dialect.name
        bucket = time_bucket(InverterSample.ts, resolution.value, dialect).label("ts")
        stmt = (
            select(
                bucket,
                func.round(func.avg(InverterSample.pv_power_w)).label("pv_power_w"),
                func.round(func.avg(InverterSample.battery_power_w)).label("battery_power_w"),
                func.round(func.avg(InverterSample.grid_power_w)).label("grid_power_w"),
                func.round(func.avg(InverterSample.load_power_w)).label("load_power_w"),
                func.round(func.avg(InverterSample.inverter_power_w)).label("inverter_power_w"),
                func.round(func.avg(InverterSample.battery_soc_pct), 2).label("battery_soc_pct"),
                func.round(func.avg(InverterSample.battery_temp_c), 1).label("battery_temp_c"),
            )
            .where(
                InverterSample.inverter_id == inverter_id,
                InverterSample.ts >= from_,
                InverterSample.ts <= to,
            )
            .group_by(bucket)
            .order_by(bucket)
        )
        rows = (await session.execute(stmt)).all()

    return [
        {
            "ts": serialize_bucket_ts(row.ts),
            "pv_power_w": _maybe_int(row.pv_power_w),
            "battery_power_w": _maybe_int(row.battery_power_w),
            "grid_power_w": _maybe_int(row.grid_power_w),
            "load_power_w": _maybe_int(row.load_power_w),
            "inverter_power_w": _maybe_int(row.inverter_power_w),
            "battery_soc_pct": _maybe_float(row.battery_soc_pct),
            "battery_temp_c": _maybe_float(row.battery_temp_c),
        }
        for row in rows
    ]

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import AppState, get_state
from app.api.schemas import SettingsUpdate
from app.core.settings_store import DEFAULT_SETTINGS

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings(state: AppState = Depends(get_state)) -> dict[str, Any]:
    return await state.settings_store.get_all()


@router.put("/settings")
async def put_settings(
    body: SettingsUpdate,
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    values = body.model_dump(exclude_none=True)
    if not values:
        return await state.settings_store.get_all()
    try:
        settings = await state.settings_store.update(values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    state.discovery.configure(
        concurrency=settings.get("discovery_concurrency"),
        port_scan_timeout=settings.get("discovery_port_scan_timeout"),
        probe_timeout=settings.get("discovery_probe_timeout"),
        subnet_prefix_length=settings.get("discovery_subnet_prefix_length"),
    )
    interval = settings.get(
        "recorder_interval_seconds", DEFAULT_SETTINGS["recorder_interval_seconds"]
    )
    state.supervisor.set_recorder_interval(float(interval))
    return settings

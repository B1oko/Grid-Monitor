import asyncio

from fastapi import APIRouter, Depends

from app.api.deps import AppState, get_state
from app.services.discovery import DiscoveryResult, DiscoveryStatus

router = APIRouter(prefix="/api", tags=["discovery"])


@router.get("/discovery")
async def get_discovery(state: AppState = Depends(get_state)) -> dict[str, object]:
    last_result = state.discovery.last_result
    return {
        "in_progress": state.discovery.in_progress,
        "result": last_result.to_dict() if last_result else None,
    }


@router.post("/discover")
async def run_discovery(state: AppState = Depends(get_state)) -> dict[str, object]:
    started = not state.discovery.in_progress
    if started:
        asyncio.create_task(state.discovery.discover())

    last_result = state.discovery.last_result
    result = last_result or DiscoveryResult(
        status=DiscoveryStatus.SEARCHING,
        message="Scanning local network",
    )
    return {
        "in_progress": started or state.discovery.in_progress,
        "result": result.to_dict(),
    }

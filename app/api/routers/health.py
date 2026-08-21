from fastapi import APIRouter, Depends

from app import __version__
from app.api.deps import AppState, get_state

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(state: AppState = Depends(get_state)) -> dict[str, object]:
    last_result = state.discovery.last_result
    return {
        "ok": True,
        "version": __version__,
        "clients": state.hub.client_count,
        "polling": state.hub.is_polling,
        "inverters": state.supervisor.list_status(),
        "discovery_status": last_result.status if last_result else None,
        "discovery_in_progress": state.discovery.in_progress,
    }

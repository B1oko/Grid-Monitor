from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.api.deps import AppState, get_state
from app.api.schemas import AlertEventOut
from app.db.models import AlertEvent

router = APIRouter(prefix="/api", tags=["alerts"])


@router.get("/alerts", response_model=list[AlertEventOut])
async def list_alerts(
    limit: int = Query(default=50, ge=1, le=500),
    active: bool = False,
    state: AppState = Depends(get_state),
) -> list[AlertEvent]:
    query = select(AlertEvent).order_by(AlertEvent.notified_at.desc()).limit(limit)
    if active:
        query = query.where(AlertEvent.resolved_at.is_(None))
    async with state.session_factory() as session:
        return list((await session.execute(query)).scalars().all())

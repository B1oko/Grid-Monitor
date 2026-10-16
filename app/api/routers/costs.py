from datetime import UTC, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import AppState, get_state
from app.api.schemas import TariffIn, TariffOut
from app.db.models import Tariff
from app.services.costs import estimate_costs
from app.services.energy import hourly_energy

router = APIRouter(prefix="/api", tags=["costs"])

DUPLICATE_DATE = "A tariff already starts on that date"


@router.get("/tariffs", response_model=list[TariffOut])
async def list_tariffs(state: AppState = Depends(get_state)) -> list[Tariff]:
    async with state.session_factory() as session:
        result = await session.execute(select(Tariff).order_by(Tariff.valid_from.desc()))
        return list(result.scalars().all())


@router.post("/tariffs", response_model=TariffOut, status_code=201)
async def create_tariff(body: TariffIn, state: AppState = Depends(get_state)) -> Tariff:
    tariff = Tariff(**body.model_dump())
    async with state.session_factory() as session:
        session.add(tariff)
        try:
            await session.commit()
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail=DUPLICATE_DATE) from exc
        await session.refresh(tariff)
        return tariff


@router.put("/tariffs/{tariff_id}", response_model=TariffOut)
async def update_tariff(
    tariff_id: int, body: TariffIn, state: AppState = Depends(get_state)
) -> Tariff:
    async with state.session_factory() as session:
        tariff = await session.get(Tariff, tariff_id)
        if tariff is None:
            raise HTTPException(status_code=404, detail="Tariff not found")
        for key, value in body.model_dump().items():
            setattr(tariff, key, value)
        try:
            await session.commit()
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail=DUPLICATE_DATE) from exc
        await session.refresh(tariff)
        return tariff


@router.delete("/tariffs/{tariff_id}", status_code=204)
async def delete_tariff(tariff_id: int, state: AppState = Depends(get_state)) -> Response:
    async with state.session_factory() as session:
        tariff = await session.get(Tariff, tariff_id)
        if tariff is None:
            raise HTTPException(status_code=404, detail="Tariff not found")
        await session.delete(tariff)
        await session.commit()
    return Response(status_code=204)


@router.get("/costs")
async def get_costs(
    inverter_id: Annotated[int, Query()],
    from_: Annotated[datetime, Query(alias="from")],
    to: Annotated[datetime, Query()],
    state: AppState = Depends(get_state),
    tz: Annotated[str, Query(description="IANA time zone of the supply point")] = "UTC",
) -> dict[str, Any]:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Unknown time zone {tz!r}") from exc
    start, end = (value if value.tzinfo else value.replace(tzinfo=UTC) for value in (from_, to))
    if end <= start:
        raise HTTPException(status_code=422, detail="'to' must be after 'from'")
    now = datetime.now(UTC)
    async with state.session_factory() as session:
        tariffs = (await session.execute(select(Tariff))).scalars().all()
        hours = await hourly_energy(
            session,
            dialect=state.engine.dialect.name,
            inverter_id=inverter_id,
            start=start,
            end=end,
            now=now,
        )
    return estimate_costs(hours, tariffs, start=start, end=end, now=now, tz=zone)

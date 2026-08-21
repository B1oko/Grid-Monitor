from fastapi import APIRouter

from app.drivers.registry import list_drivers

router = APIRouter(prefix="/api", tags=["drivers"])


@router.get("/drivers")
async def get_drivers() -> list[dict[str, object]]:
    return [
        {
            "id": meta.id,
            "name": meta.name,
            "manufacturer": meta.manufacturer,
            "protocol": meta.protocol,
            "default_port": meta.default_port,
            "default_unit_id": meta.default_unit_id,
        }
        for meta in list_drivers()
    ]

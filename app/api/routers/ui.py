from pathlib import Path

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from app.api.deps import AppState
from app.i18n import LOCALES_DIR, available_languages, catalog

router = APIRouter(tags=["ui"])
STATIC_DIR = Path(__file__).resolve().parents[2] / "web" / "static"


@router.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/manifest.json")
async def manifest_json() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@router.get("/sw.js")
async def service_worker_js() -> FileResponse:
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@router.get("/i18n/languages.json")
async def languages() -> list[dict[str, str]]:
    return [
        {"code": code, "name": catalog(code).get("meta.language_name", code)}
        for code in available_languages()
    ]


@router.get("/i18n/{language}.json")
async def locale(language: str) -> FileResponse:
    if language not in available_languages():
        raise HTTPException(status_code=404, detail="Unknown language")
    return FileResponse(LOCALES_DIR / f"{language}.json", media_type="application/json")


@router.websocket("/ws/live")
async def live(websocket: WebSocket) -> None:
    state: AppState = websocket.app.state.core
    await state.hub.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await state.hub.disconnect(websocket)
    except Exception:
        await state.hub.disconnect(websocket)

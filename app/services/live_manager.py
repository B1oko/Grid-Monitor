from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Protocol

from fastapi import WebSocket


class Readable(Protocol):
    async def read(self) -> Any: ...

    async def close(self) -> None: ...


class LiveHub:
    """Shared WebSocket fan-out. Live polling runs only while clients are connected."""

    def __init__(self) -> None:
        self._websockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._on_first: Callable[[], Awaitable[None]] | None = None
        self._on_last: Callable[[], Awaitable[None]] | None = None

    def set_hooks(
        self,
        *,
        on_first: Callable[[], Awaitable[None]],
        on_last: Callable[[], Awaitable[None]],
    ) -> None:
        self._on_first = on_first
        self._on_last = on_last

    @property
    def client_count(self) -> int:
        return len(self._websockets)

    @property
    def is_polling(self) -> bool:
        return self.client_count > 0

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        start = False
        async with self._lock:
            self._websockets.add(websocket)
            start = len(self._websockets) == 1
        if start and self._on_first:
            await self._on_first()

    async def disconnect(self, websocket: WebSocket) -> None:
        stop = False
        async with self._lock:
            self._websockets.discard(websocket)
            stop = not self._websockets
        if stop and self._on_last:
            await self._on_last()

    async def shutdown(self) -> None:
        async with self._lock:
            sockets = list(self._websockets)
            self._websockets.clear()
        for websocket in sockets:
            try:
                await websocket.close()
            except Exception:
                pass

    async def broadcast(self, message: dict[str, Any]) -> None:
        async with self._lock:
            sockets = list(self._websockets)

        stale: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)

        if stale:
            stop = False
            async with self._lock:
                for websocket in stale:
                    self._websockets.discard(websocket)
                stop = not self._websockets
            if stop and self._on_last:
                await self._on_last()


class LivePoller:
    def __init__(
        self,
        *,
        inverter_id: int,
        driver: Readable,
        hub: LiveHub,
        poll_interval_seconds: float,
    ) -> None:
        self._inverter_id = inverter_id
        self._driver = driver
        self._hub = hub
        self._poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None

    @property
    def poll_interval_seconds(self) -> float:
        return self._poll_interval_seconds

    def set_poll_interval(self, seconds: float) -> None:
        self._poll_interval_seconds = seconds

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name=f"live-{self._inverter_id}")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        try:
            while True:
                try:
                    reading = await self._driver.read()
                    payload = reading.model_dump(mode="json")
                    await self._hub.broadcast(
                        {
                            "type": "sample",
                            "inverter_id": self._inverter_id,
                            "data": payload,
                        }
                    )
                except Exception as exc:
                    await self._hub.broadcast(
                        {
                            "type": "error",
                            "inverter_id": self._inverter_id,
                            "data": {
                                "connected": False,
                                "timestamp": datetime.now(UTC).isoformat(),
                                "message": str(exc),
                            },
                        }
                    )
                await asyncio.sleep(self._poll_interval_seconds)
        except asyncio.CancelledError:
            raise

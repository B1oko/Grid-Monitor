from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings_store import SettingsStore
from app.services.discovery import InverterDiscovery
from app.services.live_manager import LiveHub
from app.services.retention import RetentionService
from app.services.supervisor import InverterSupervisor


@dataclass
class AppState:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    settings_store: SettingsStore
    supervisor: InverterSupervisor
    hub: LiveHub
    discovery: InverterDiscovery
    retention: RetentionService
    retention_task: object | None = field(default=None)


async def get_state(request: Request) -> AppState:
    return request.app.state.core

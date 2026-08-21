from __future__ import annotations

import asyncio

from pymodbus.client import AsyncModbusTcpClient


class ModbusTcpTransport:
    """Shared Modbus TCP connection with reconnect-on-error semantics."""

    def __init__(self, host: str, port: int, unit_id: int, timeout_seconds: float) -> None:
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout_seconds = timeout_seconds
        self._client: AsyncModbusTcpClient | None = None
        self._lock = asyncio.Lock()

    async def read_holding_registers(self, address: int, count: int) -> list[int]:
        async with self._lock:
            try:
                client = await self._ensure_connected_unlocked()
                response = await client.read_holding_registers(
                    address=address,
                    count=count,
                    slave=self.unit_id,
                )
                if response.isError():
                    raise RuntimeError(f"Modbus error response: {response}")
                return list(response.registers)
            except Exception:
                await self._close_unlocked()
                raise

    async def close(self) -> None:
        async with self._lock:
            await self._close_unlocked()

    async def _ensure_connected_unlocked(self) -> AsyncModbusTcpClient:
        if self._client and self._client.connected:
            return self._client

        self._client = AsyncModbusTcpClient(
            host=self.host,
            port=self.port,
            timeout=self.timeout_seconds,
        )
        connected = await self._client.connect()
        if not connected:
            await self._close_unlocked()
            raise ConnectionError(f"Unable to connect to {self.host}:{self.port}")
        return self._client

    async def _close_unlocked(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

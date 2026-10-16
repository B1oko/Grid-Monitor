import asyncio
import socket

import pytest
from pymodbus.datastore import ModbusDeviceContext, ModbusSequentialDataBlock, ModbusServerContext
from pymodbus.server import ModbusTcpServer

from app.drivers.transports.modbus_tcp import ModbusTcpTransport

UNIT_ID = 3


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
async def modbus_server():
    # Holding register n holds n + 100 for unit 3 only. Data blocks are
    # 1-based: the block starting at 1 begins with register 0.
    block = ModbusSequentialDataBlock(1, [n + 100 for n in range(64)])
    context = ModbusServerContext(devices={UNIT_ID: ModbusDeviceContext(hr=block)}, single=False)
    port = _free_port()
    server = ModbusTcpServer(context, address=("127.0.0.1", port))
    task = asyncio.create_task(server.serve_forever())
    for _ in range(50):
        if server.is_active():
            break
        await asyncio.sleep(0.02)
    yield port
    await server.shutdown()
    task.cancel()


async def test_reads_holding_registers_from_a_real_server(modbus_server: int) -> None:
    transport = ModbusTcpTransport("127.0.0.1", modbus_server, UNIT_ID, timeout_seconds=2)
    try:
        assert await transport.read_holding_registers(10, 4) == [110, 111, 112, 113]
    finally:
        await transport.close()

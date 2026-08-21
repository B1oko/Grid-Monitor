from app.drivers.base import InverterReading
from app.services.live_manager import LiveHub, LivePoller


class FakeDriver:
    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1

    async def read(self) -> InverterReading:
        return InverterReading(pv_power_w=100, connected=True)


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict[str, object]] = []
        self.closed = False

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict[str, object]) -> None:
        self.messages.append(message)

    async def close(self) -> None:
        self.closed = True


async def test_connect_starts_polling_and_last_disconnect_stops_it() -> None:
    driver = FakeDriver()
    hub = LiveHub()
    started = {"value": False}
    stopped = {"value": False}

    async def on_first() -> None:
        started["value"] = True

    async def on_last() -> None:
        stopped["value"] = True

    hub.set_hooks(on_first=on_first, on_last=on_last)
    websocket = FakeWebSocket()

    await hub.connect(websocket)  # type: ignore[arg-type]
    assert websocket.accepted is True
    assert hub.client_count == 1
    assert hub.is_polling is True
    assert started["value"] is True

    await hub.disconnect(websocket)  # type: ignore[arg-type]
    assert hub.client_count == 0
    assert hub.is_polling is False
    assert stopped["value"] is True

    poller = LivePoller(inverter_id=1, driver=driver, hub=hub, poll_interval_seconds=60)
    await poller.start()
    await poller.stop()

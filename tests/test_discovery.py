from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.drivers.base import DriverMeta, InverterDriver, InverterReading
from app.drivers.registry import register_driver
from app.services.discovery import (
    DiscoveryStatus,
    InverterDiscovery,
    get_local_subnet,
    iter_subnet_hosts,
    probe_drivers,
)


def test_iter_subnet_hosts_returns_usable_hosts() -> None:
    hosts = iter_subnet_hosts("192.168.1.0/30")
    assert hosts == ["192.168.1.1", "192.168.1.2"]


def test_get_local_subnet_uses_prefix_length() -> None:
    with patch("app.services.discovery.socket.socket") as socket_cls:
        sock = MagicMock()
        sock.getsockname.return_value = ("10.0.0.15", 54321)
        socket_cls.return_value.__enter__.return_value = sock
        assert get_local_subnet(24) == "10.0.0.0/24"


@pytest.mark.asyncio
async def test_probe_drivers_returns_matching_driver() -> None:
    @register_driver
    class ProbeDriver(InverterDriver):
        meta = DriverMeta(id="probe-test", name="Probe", manufacturer="Test", protocol="test")

        async def read(self) -> InverterReading:
            return InverterReading()

        @classmethod
        async def probe(
            cls, host: str, *, port: int = 502, unit_id: int = 1, timeout: float = 2.0
        ) -> bool:
            return host.endswith(".20")

    candidates = await probe_drivers("192.168.1.20")
    ids = {item.driver_id for item in candidates}
    assert "probe-test" in ids
    assert not await ProbeDriver.probe("192.168.1.10")


@pytest.mark.asyncio
async def test_discover_inverter_returns_found_candidate() -> None:
    discovery = InverterDiscovery(concurrency=2)

    async def fake_probe(host: str, *, port: int = 502, timeout: float = 2.0):
        if host == "192.168.1.20":
            from app.services.discovery import DiscoveryCandidate

            return [DiscoveryCandidate(host=host, driver_id="saj-h2", latency_ms=8.5, port=port)]
        return []

    with (
        patch.object(
            discovery, "_scan_open_ports", AsyncMock(return_value=["192.168.1.10", "192.168.1.20"])
        ),
        patch("app.services.discovery.probe_drivers", side_effect=fake_probe),
        patch("app.services.discovery.get_local_subnet", return_value="192.168.1.0/24"),
    ):
        result = await discovery.discover()

    assert result.status == DiscoveryStatus.FOUND
    assert result.host == "192.168.1.20"
    assert result.driver_id == "saj-h2"
    assert result.candidates[0].driver_id == "saj-h2"


@pytest.mark.asyncio
async def test_discover_inverter_returns_not_found() -> None:
    discovery = InverterDiscovery(concurrency=2)

    with (
        patch.object(discovery, "_scan_open_ports", AsyncMock(return_value=["192.168.1.10"])),
        patch("app.services.discovery.probe_drivers", AsyncMock(return_value=[])),
        patch("app.services.discovery.get_local_subnet", return_value="192.168.1.0/24"),
    ):
        result = await discovery.discover()

    assert result.status == DiscoveryStatus.NOT_FOUND
    assert result.host is None

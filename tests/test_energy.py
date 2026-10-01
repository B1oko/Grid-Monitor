from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.db.engine import apply_migrations, make_engine, make_session_factory
from app.db.models import Inverter, InverterSample
from app.services.energy import energy_totals

MADRID = ZoneInfo("Europe/Madrid")


@pytest.fixture
async def factory(tmp_path):
    engine = make_engine(f"sqlite+aiosqlite:///{(tmp_path / 'energy.db').as_posix()}")
    await apply_migrations(engine)
    yield make_session_factory(engine)
    await engine.dispose()


async def _add(factory, samples: list[tuple[datetime, dict]]) -> int:
    async with factory() as session:
        inverter = Inverter(name="A", driver_id="saj-h2", host="192.0.2.1")
        session.add(inverter)
        await session.flush()
        session.add_all(InverterSample(inverter_id=inverter.id, ts=ts, **v) for ts, v in samples)
        await session.commit()
        return inverter.id


async def _totals(factory, inverter_id, start, end, resolution="day", now=None):
    async with factory() as session:
        return await energy_totals(
            session,
            dialect="sqlite",
            inverter_id=inverter_id,
            start=start,
            end=end,
            tz=MADRID,
            resolution=resolution,
            now=now or end,
        )


async def test_signed_flows_are_split_by_direction(factory) -> None:
    hour = datetime(2026, 7, 1, 10, tzinfo=UTC)
    # Within one hour the grid imports 1 kW half the time and exports 1 kW the
    # other half. A plain average would report zero.
    samples = [
        (
            hour + timedelta(minutes=m),
            {
                "grid_power_w": 1000 if m < 30 else -1000,
                "battery_power_w": -2000 if m < 30 else 500,
                "pv_power_w": 3000,
                "load_power_w": 1500,
            },
        )
        for m in range(0, 60, 5)
    ]
    inverter_id = await _add(factory, samples)

    [day] = await _totals(
        factory, inverter_id, hour - timedelta(hours=10), hour + timedelta(hours=10)
    )

    assert day["solar_kwh"] == 3.0
    assert day["home_kwh"] == 1.5
    assert day["grid_import_kwh"] == 0.5
    assert day["grid_export_kwh"] == 0.5
    assert day["battery_charge_kwh"] == 1.0
    assert day["battery_discharge_kwh"] == 0.25


async def test_days_follow_the_requested_time_zone(factory) -> None:
    # 22:30 UTC on 1 July is 00:30 on 2 July in Madrid (UTC+2).
    early = datetime(2026, 7, 1, 21, 30, tzinfo=UTC)
    late = datetime(2026, 7, 1, 22, 30, tzinfo=UTC)
    inverter_id = await _add(
        factory, [(early, {"load_power_w": 1000}), (late, {"load_power_w": 2000})]
    )

    rows = await _totals(
        factory,
        inverter_id,
        datetime(2026, 6, 30, 22, tzinfo=UTC),
        datetime(2026, 7, 3, tzinfo=UTC),
    )

    assert [(row["ts"], row["home_kwh"]) for row in rows] == [
        ("2026-07-01T00:00:00+02:00", 1.0),
        ("2026-07-02T00:00:00+02:00", 2.0),
    ]
    assert rows[0]["solar_kwh"] is None


async def test_current_hour_counts_only_elapsed_time(factory) -> None:
    hour = datetime(2026, 7, 1, 10, tzinfo=UTC)
    inverter_id = await _add(factory, [(hour + timedelta(minutes=5), {"pv_power_w": 4000})])

    [day] = await _totals(
        factory,
        inverter_id,
        hour - timedelta(hours=10),
        hour + timedelta(days=1),
        now=hour + timedelta(minutes=15),
    )

    assert day["solar_kwh"] == 1.0


async def test_months_group_days(factory) -> None:
    samples = [
        (datetime(2026, month, day, 12, tzinfo=UTC), {"pv_power_w": 1000})
        for month, day in [(1, 5), (1, 20), (2, 3)]
    ]
    inverter_id = await _add(factory, samples)

    rows = await _totals(
        factory,
        inverter_id,
        datetime(2025, 12, 31, 23, tzinfo=UTC),
        datetime(2026, 12, 31, tzinfo=UTC),
        resolution="month",
    )

    assert [(row["ts"], row["solar_kwh"]) for row in rows] == [
        ("2026-01-01T00:00:00+01:00", 2.0),
        ("2026-02-01T00:00:00+01:00", 1.0),
    ]


def test_energy_endpoint_validates_time_zone(client: TestClient) -> None:
    params = {"inverter_id": 1, "from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z"}
    assert client.get("/api/energy", params=params | {"tz": "Europe/Madrid"}).json() == []
    assert client.get("/api/energy", params=params | {"tz": "Mars/Base"}).status_code == 422

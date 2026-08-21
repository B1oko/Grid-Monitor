from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import column

from app.db.timebucket import serialize_bucket_ts, time_bucket


def test_health_and_drivers(client: TestClient) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["ok"] is True
    assert payload["inverters"] == []

    drivers = client.get("/api/drivers")
    assert drivers.status_code == 200
    ids = {item["id"] for item in drivers.json()}
    assert "saj-h2" in ids


def test_inverter_crud_and_settings(client: TestClient) -> None:
    created = client.post(
        "/api/inverters",
        json={
            "name": "Garage",
            "driver_id": "saj-h2",
            "host": "192.0.2.10",
            "port": 502,
            "battery_capacity_kwh": 10,
        },
    )
    assert created.status_code == 201
    inverter = created.json()
    assert inverter["host"] == "192.0.2.10"

    listed = client.get("/api/inverters")
    assert len(listed.json()) == 1

    patched = client.patch(
        f"/api/inverters/{inverter['id']}",
        json={"poll_interval_s": 5, "name": "Roof"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Roof"
    assert patched.json()["poll_interval_s"] == 5

    settings = client.put("/api/settings", json={"retention_days": 90})
    assert settings.status_code == 200
    assert settings.json()["retention_days"] == 90

    history = client.get(
        "/api/history",
        params={
            "inverter_id": inverter["id"],
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-01-02T00:00:00Z",
            "resolution": "hour",
        },
    )
    assert history.status_code == 200
    assert history.json() == []

    deleted = client.delete(f"/api/inverters/{inverter['id']}")
    assert deleted.status_code == 204
    assert client.get("/api/inverters").json() == []


def test_unknown_driver_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/inverters",
        json={"name": "X", "driver_id": "nope", "host": "192.0.2.1"},
    )
    assert response.status_code == 400


def test_time_bucket_sqlite_and_postgres() -> None:
    col = column("ts")
    sqlite_expr = str(time_bucket(col, "hour", "sqlite"))
    pg_expr = str(time_bucket(col, "hour", "postgresql"))
    assert "strftime" in sqlite_expr
    assert "date_trunc" in pg_expr
    serialized = serialize_bucket_ts("2026-08-21 15:00:00")
    assert serialized.startswith("2026-08-21T15:00:00")
    assert serialize_bucket_ts(datetime(2026, 8, 21, 15, tzinfo=UTC)).startswith("2026-08-21")

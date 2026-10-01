from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.schemas import AlertEventOut
from app.core.settings_store import DEFAULT_SETTINGS, SettingsStore
from app.db.engine import apply_migrations, make_engine, make_session_factory
from app.db.models import AlertEvent, Inverter
from app.drivers.base import InverterReading
from app.services.alerts import (
    AlertService,
    Evaluation,
    NoProductionRule,
    OverloadRule,
    Signal,
    Tracker,
)
from app.services.notifier import Notification
from app.services.sun import solar_elevation

LOCATION = (39.47, -0.38)
NOON_JUNE = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
MIDNIGHT_JUNE = datetime(2026, 6, 21, 23, 30, tzinfo=UTC)


def cfg(**overrides: object) -> dict[str, object]:
    merged = dict(DEFAULT_SETTINGS)
    merged.update(latitude=LOCATION[0], longitude=LOCATION[1])
    merged.update(overrides)
    return merged


def test_solar_elevation_valencia() -> None:
    assert 70 < solar_elevation(*LOCATION, NOON_JUNE) < 75
    assert solar_elevation(*LOCATION, MIDNIGHT_JUNE) < -20
    assert 20 < solar_elevation(*LOCATION, datetime(2026, 12, 21, 12, 0, tzinfo=UTC)) < 30


def test_tracker_fires_after_delay_and_resolves() -> None:
    tracker = Tracker()
    t0 = NOON_JUNE
    on = Evaluation(Signal.ON, 6000)
    assert tracker.update(on, t0, 60) is None
    assert tracker.update(on, t0 + timedelta(seconds=30), 60) is None
    assert tracker.update(Evaluation(Signal.ON, 7000), t0 + timedelta(seconds=60), 60) == "fire"
    assert tracker.peak == 7000
    assert tracker.started_at == t0
    # Still on: no duplicate notification.
    assert tracker.update(on, t0 + timedelta(seconds=90), 60) is None
    # Unknown readings keep the state.
    assert tracker.update(Evaluation(None), t0 + timedelta(seconds=100), 60) is None
    off = Evaluation(Signal.OFF, 1000)
    assert tracker.update(off, t0 + timedelta(seconds=120), 60) is None
    assert tracker.update(off, t0 + timedelta(seconds=180), 60) == "resolve"
    assert not tracker.firing


def test_tracker_short_spike_does_not_fire() -> None:
    tracker = Tracker()
    t0 = NOON_JUNE
    assert tracker.update(Evaluation(Signal.ON, 6000), t0, 60) is None
    assert tracker.update(Evaluation(Signal.OFF, 3000), t0 + timedelta(seconds=30), 60) is None
    assert tracker.update(Evaluation(Signal.ON, 6000), t0 + timedelta(seconds=50), 60) is None
    assert tracker.update(Evaluation(Signal.ON, 6000), t0 + timedelta(seconds=100), 60) is None
    assert tracker.update(Evaluation(Signal.ON, 6000), t0 + timedelta(seconds=110), 60) == "fire"


def test_tracker_idle_holds_firing_alert() -> None:
    tracker = Tracker(firing=True, started_at=NOON_JUNE)
    assert tracker.update(Evaluation(Signal.IDLE), NOON_JUNE, 60) is None
    assert tracker.firing
    pending = Tracker(pending_since=NOON_JUNE)
    pending.update(Evaluation(Signal.IDLE), NOON_JUNE, 60)
    assert pending.pending_since is None


def test_overload_rule_uses_grid_import_with_hysteresis() -> None:
    rule = OverloadRule()
    config = cfg(alert_overload_limit_w=5500)
    assert rule.evaluate(InverterReading(grid_power_w=5600), NOON_JUNE, config).signal is Signal.ON
    assert rule.evaluate(InverterReading(grid_power_w=5400), NOON_JUNE, config).signal is None
    assert rule.evaluate(InverterReading(grid_power_w=5000), NOON_JUNE, config).signal is Signal.OFF
    assert (
        rule.evaluate(InverterReading(grid_power_w=-6000), NOON_JUNE, config).signal is Signal.OFF
    )
    assert rule.evaluate(None, NOON_JUNE, config).signal is None


def test_no_production_rule_only_in_daylight() -> None:
    rule = NoProductionRule()
    config = cfg()
    dark = InverterReading(pv_power_w=0)
    assert rule.evaluate(dark, NOON_JUNE, config).signal is Signal.ON
    assert rule.evaluate(dark, MIDNIGHT_JUNE, config).signal is Signal.IDLE
    assert rule.evaluate(InverterReading(pv_power_w=2500), NOON_JUNE, config).signal is Signal.OFF
    assert not rule.enabled(cfg(latitude=None))


class FakeReader:
    def __init__(self) -> None:
        self.reading: InverterReading | None = InverterReading(grid_power_w=0, pv_power_w=3000)

    async def read_recent(self, max_age_seconds: float) -> InverterReading:
        if self.reading is None:
            raise ConnectionError("timeout")
        return self.reading


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    async def send(self, notification: Notification) -> int:
        self.sent.append(notification)
        return 1


@pytest.fixture
async def alert_env(tmp_path: Path):
    engine = make_engine(f"sqlite+aiosqlite:///{(tmp_path / 'alerts.db').as_posix()}")
    await apply_migrations(engine)
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        inverter = Inverter(name="Roof", driver_id="saj-h2", host="192.0.2.10")
        session.add(inverter)
        await session.commit()
        inverter_id = inverter.id

    store = SettingsStore(session_factory)
    await store.update(
        {
            "latitude": LOCATION[0],
            "longitude": LOCATION[1],
            "alert_overload_limit_w": 5500,
            "alert_overload_minutes": 1.0,
        }
    )
    reader = FakeReader()
    runtime = SimpleNamespace(inverter=SimpleNamespace(name="Roof"), reader=reader)
    supervisor = SimpleNamespace(runtimes={inverter_id: runtime})
    notifier = FakeNotifier()
    clock = SimpleNamespace(now=NOON_JUNE)
    service = AlertService(
        session_factory=session_factory,
        settings_store=store,
        supervisor=supervisor,
        notifiers=[notifier],
        clock=lambda: clock.now,
    )
    yield SimpleNamespace(
        service=service,
        reader=reader,
        notifier=notifier,
        clock=clock,
        session_factory=session_factory,
    )
    await engine.dispose()


async def _events(session_factory) -> list[AlertEvent]:
    async with session_factory() as session:
        return list((await session.execute(select(AlertEvent))).scalars().all())


async def test_alert_service_overload_cycle(alert_env) -> None:
    env = alert_env
    env.reader.reading = InverterReading(grid_power_w=6200, pv_power_w=3000)
    for _ in range(7):
        await env.service.check_once()
        env.clock.now += timedelta(seconds=10)

    assert [n.title_key for n in env.notifier.sent] == ["alerts.overload.fire.title"]
    assert "6,200 W" in env.notifier.sent[0].render("en")["body"]
    assert "6.200 W" in env.notifier.sent[0].render("es")["body"]
    events = await _events(env.session_factory)
    assert len(events) == 1
    assert events[0].kind == "overload"
    assert events[0].resolved_at is None

    env.reader.reading = InverterReading(grid_power_w=800, pv_power_w=3000)
    for _ in range(7):
        await env.service.check_once()
        env.clock.now += timedelta(seconds=10)

    assert env.notifier.sent[-1].title_key == "alerts.overload.resolve.title"
    events = await _events(env.session_factory)
    assert events[0].resolved_at is not None
    assert events[0].peak_value == 6200
    assert events[0].params["limit_w"] == 5500
    assert events[0].title == "Contracted power exceeded"
    out = AlertEventOut.model_validate(events[0]).model_dump(mode="json")
    assert datetime.fromisoformat(out["notified_at"]).utcoffset() == timedelta(0)
    assert datetime.fromisoformat(out["resolved_at"]).utcoffset() == timedelta(0)


async def test_alert_service_offline(alert_env) -> None:
    env = alert_env
    env.reader.reading = None
    for _ in range(61):
        await env.service.check_once()
        env.clock.now += timedelta(seconds=10)
    assert [n.title_key for n in env.notifier.sent] == ["alerts.offline.fire.title"]


def test_push_api(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    key = client.get("/api/push/public-key")
    assert key.status_code == 200
    assert len(key.json()["public_key"]) > 80
    assert key.json()["subscriptions"] == 0

    sub = {
        "endpoint": "https://push.example.test/abc",
        "keys": {"p256dh": "p256", "auth": "auth"},
    }
    assert client.post("/api/push/subscribe", json=sub).status_code == 204
    assert client.post("/api/push/subscribe", json=sub).status_code == 204
    assert client.get("/api/push/public-key").json()["subscriptions"] == 1

    spanish = {
        "endpoint": "https://push.example.test/es",
        "keys": {"p256dh": "p256", "auth": "auth"},
        "language": "es-ES",
    }
    assert client.post("/api/push/subscribe", json=spanish).status_code == 204

    sent: list[dict] = []
    monkeypatch.setattr("app.services.notifier.webpush", lambda **kwargs: sent.append(kwargs))
    result = client.post("/api/push/test")
    assert result.json() == {"delivered": 2}
    bodies = {s["subscription_info"]["endpoint"]: json.loads(s["data"])["body"] for s in sent}
    assert bodies[sub["endpoint"]].startswith("Test notification")
    assert bodies[spanish["endpoint"]].startswith("Notificación de prueba")
    assert (
        client.post("/api/push/unsubscribe", json={"endpoint": spanish["endpoint"]}).status_code
        == 204
    )

    assert (
        client.post("/api/push/unsubscribe", json={"endpoint": sub["endpoint"]}).status_code == 204
    )
    assert client.get("/api/push/public-key").json()["subscriptions"] == 0

    assert client.get("/api/alerts").json() == []
    settings = client.put(
        "/api/settings", json={"alert_overload_limit_w": 4600, "latitude": 39.47}
    ).json()
    assert settings["alert_overload_limit_w"] == 4600
    assert settings["latitude"] == 39.47

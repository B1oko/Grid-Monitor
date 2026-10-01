"""Background alert rules: grid overload, no solar production in daylight, inverter offline."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.settings_store import SettingsStore
from app.db.models import AlertEvent
from app.drivers.base import InverterReading
from app.services.notifier import Notification, Notifier
from app.services.sun import solar_elevation

logger = logging.getLogger(__name__)

RESOLVE_AFTER_SECONDS = 60.0
OVERLOAD_HYSTERESIS = 0.05


class Signal(Enum):
    ON = "on"  # condition holds
    OFF = "off"  # condition clearly does not hold
    IDLE = "idle"  # rule not applicable right now: forget pending state, keep a firing alert


@dataclass(frozen=True)
class Evaluation:
    signal: Signal | None  # None = no information (keep current state)
    value: float | None = None


@dataclass
class Tracker:
    pending_since: datetime | None = None
    clear_since: datetime | None = None
    started_at: datetime | None = None
    firing: bool = False
    event_id: int | None = None
    peak: float | None = None

    def update(
        self, evaluation: Evaluation, now: datetime, fire_after_seconds: float
    ) -> str | None:
        """Advance the state machine. Returns "fire", "resolve" or None."""
        signal = evaluation.signal
        if signal is None:
            return None

        if signal is Signal.ON:
            self.clear_since = None
            if evaluation.value is not None:
                self.peak = (
                    evaluation.value if self.peak is None else max(self.peak, evaluation.value)
                )
            if self.firing:
                return None
            if self.pending_since is None:
                self.pending_since = now
            if (now - self.pending_since).total_seconds() >= fire_after_seconds:
                self.firing = True
                self.started_at = self.pending_since
                self.pending_since = None
                return "fire"
            return None

        self.pending_since = None
        if not self.firing:
            self.peak = None
            return None
        if signal is Signal.IDLE:
            self.clear_since = None
            return None
        if self.clear_since is None:
            self.clear_since = now
        if (now - self.clear_since).total_seconds() >= RESOLVE_AFTER_SECONDS:
            self.firing = False
            self.clear_since = None
            return "resolve"
        return None


class Rule(Protocol):
    kind: str

    def enabled(self, cfg: dict[str, Any]) -> bool: ...

    def fire_after_seconds(self, cfg: dict[str, Any]) -> float: ...

    def evaluate(
        self, reading: InverterReading | None, now: datetime, cfg: dict[str, Any]
    ) -> Evaluation: ...

    def fire_message(
        self, name: str, tracker: Tracker, now: datetime, cfg: dict[str, Any]
    ) -> tuple[str, str]: ...

    def resolve_message(
        self, name: str, tracker: Tracker, now: datetime, cfg: dict[str, Any]
    ) -> tuple[str, str]: ...


def _minutes(start: datetime | None, end: datetime) -> str:
    if start is None:
        return "?"
    total = max(0, round((end - start).total_seconds() / 60))
    if total < 60:
        return f"{total} min"
    return f"{total // 60} h {total % 60:02d} min"


def _watts(value: float | None) -> str:
    return "--" if value is None else f"{round(value):,} W"


class OverloadRule:
    """Grid import above the contracted power (positive grid power = import)."""

    kind = "overload"

    def enabled(self, cfg: dict[str, Any]) -> bool:
        return bool(cfg.get("alert_overload_enabled"))

    def fire_after_seconds(self, cfg: dict[str, Any]) -> float:
        return float(cfg["alert_overload_minutes"]) * 60

    def evaluate(
        self, reading: InverterReading | None, now: datetime, cfg: dict[str, Any]
    ) -> Evaluation:
        if reading is None or reading.grid_power_w is None:
            return Evaluation(None)
        limit = float(cfg["alert_overload_limit_w"])
        grid = float(reading.grid_power_w)
        if grid > limit:
            return Evaluation(Signal.ON, grid)
        if grid < limit * (1 - OVERLOAD_HYSTERESIS):
            return Evaluation(Signal.OFF, grid)
        return Evaluation(None, grid)

    def fire_message(self, name, tracker, now, cfg):
        limit = float(cfg["alert_overload_limit_w"])
        return (
            "Contracted power exceeded",
            f"{name}: importing {_watts(tracker.peak)} from the grid "
            f"(limit {_watts(limit)}) for {_minutes(tracker.started_at, now)}.",
        )

    def resolve_message(self, name, tracker, now, cfg):
        return (
            "Grid import back under the limit",
            f"{name}: peak {_watts(tracker.peak)}, lasted {_minutes(tracker.started_at, now)}.",
        )


class NoProductionRule:
    """No PV output while the sun is well above the horizon."""

    kind = "no_production"

    def enabled(self, cfg: dict[str, Any]) -> bool:
        return (
            bool(cfg.get("alert_no_pv_enabled"))
            and cfg.get("latitude") is not None
            and cfg.get("longitude") is not None
        )

    def fire_after_seconds(self, cfg: dict[str, Any]) -> float:
        return float(cfg["alert_no_pv_minutes"]) * 60

    def evaluate(
        self, reading: InverterReading | None, now: datetime, cfg: dict[str, Any]
    ) -> Evaluation:
        elevation = solar_elevation(float(cfg["latitude"]), float(cfg["longitude"]), now)
        if elevation < float(cfg["alert_no_pv_min_sun_elevation_deg"]):
            return Evaluation(Signal.IDLE)
        if reading is None or reading.pv_power_w is None:
            return Evaluation(None)
        pv = float(reading.pv_power_w)
        if pv < float(cfg["alert_no_pv_threshold_w"]):
            return Evaluation(Signal.ON)
        return Evaluation(Signal.OFF, pv)

    def fire_message(self, name, tracker, now, cfg):
        return (
            "No solar production",
            f"{name}: solar output has been under {_watts(cfg['alert_no_pv_threshold_w'])} "
            f"for {_minutes(tracker.started_at, now)} in daylight. "
            "Check the inverter breaker and the PV isolator.",
        )

    def resolve_message(self, name, tracker, now, cfg):
        return (
            "Solar production restored",
            f"{name}: PV is producing again after {_minutes(tracker.started_at, now)}.",
        )


class OfflineRule:
    """The inverter stopped answering."""

    kind = "offline"

    def enabled(self, cfg: dict[str, Any]) -> bool:
        return bool(cfg.get("alert_offline_enabled"))

    def fire_after_seconds(self, cfg: dict[str, Any]) -> float:
        return float(cfg["alert_offline_minutes"]) * 60

    def evaluate(
        self, reading: InverterReading | None, now: datetime, cfg: dict[str, Any]
    ) -> Evaluation:
        return Evaluation(Signal.ON if reading is None else Signal.OFF)

    def fire_message(self, name, tracker, now, cfg):
        return (
            "Inverter not responding",
            f"{name}: no Modbus response for {_minutes(tracker.started_at, now)}. "
            "It may have lost power or network.",
        )

    def resolve_message(self, name, tracker, now, cfg):
        return (
            "Inverter back online",
            f"{name}: responding again after {_minutes(tracker.started_at, now)}.",
        )


DEFAULT_RULES: tuple[Rule, ...] = (OverloadRule(), NoProductionRule(), OfflineRule())


class ReaderLike(Protocol):
    async def read_recent(self, max_age_seconds: float) -> InverterReading: ...


class RuntimeLike(Protocol):
    inverter: Any
    reader: ReaderLike


class SupervisorLike(Protocol):
    @property
    def runtimes(self) -> dict[int, RuntimeLike]: ...


class AlertService:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings_store: SettingsStore,
        supervisor: SupervisorLike,
        notifiers: Iterable[Notifier],
        rules: Iterable[Rule] = DEFAULT_RULES,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session_factory = session_factory
        self._settings_store = settings_store
        self._supervisor = supervisor
        self._notifiers = list(notifiers)
        self._rules = list(rules)
        self._clock = clock
        self._trackers: dict[tuple[int, str], Tracker] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self._close_stale_events()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="alerts")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _loop(self) -> None:
        while True:
            interval = 10.0
            try:
                cfg = await self._settings_store.get_all()
                interval = float(cfg["alerts_check_interval_seconds"])
                await self.check_once(cfg)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Alert check failed")
            await asyncio.sleep(interval)

    async def check_once(self, cfg: dict[str, Any] | None = None) -> None:
        if cfg is None:
            cfg = await self._settings_store.get_all()
        max_age = float(cfg["alerts_check_interval_seconds"])
        runtimes = dict(self._supervisor.runtimes)

        for key in [k for k in self._trackers if k[0] not in runtimes]:
            self._trackers.pop(key)

        for inverter_id, runtime in runtimes.items():
            try:
                reading: InverterReading | None = await runtime.reader.read_recent(max_age)
            except Exception as exc:
                logger.debug("Alerts: inverter %s unreadable: %s", inverter_id, exc)
                reading = None
            now = self._clock()

            for rule in self._rules:
                key = (inverter_id, rule.kind)
                tracker = self._trackers.setdefault(key, Tracker())
                if not rule.enabled(cfg):
                    if tracker.firing:
                        await self._mark_resolved(tracker, now)
                    self._trackers[key] = Tracker()
                    continue

                action = tracker.update(
                    rule.evaluate(reading, now, cfg), now, rule.fire_after_seconds(cfg)
                )
                if action is None:
                    continue
                name = runtime.inverter.name
                if action == "fire":
                    title, body = rule.fire_message(name, tracker, now, cfg)
                    tracker.event_id = await self._record_event(
                        inverter_id, rule.kind, title, body, tracker, now
                    )
                else:
                    title, body = rule.resolve_message(name, tracker, now, cfg)
                    await self._mark_resolved(tracker, now)
                    tracker.peak = None
                    tracker.started_at = None
                await self._notify(Notification(title, body, tag=f"{rule.kind}-{inverter_id}"))

    async def _notify(self, notification: Notification) -> None:
        logger.info("Alert: %s - %s", notification.title, notification.body)
        for notifier in self._notifiers:
            try:
                await notifier.send(notification)
            except Exception:
                logger.exception("Notifier %s failed", type(notifier).__name__)

    async def _record_event(
        self,
        inverter_id: int,
        kind: str,
        title: str,
        message: str,
        tracker: Tracker,
        now: datetime,
    ) -> int | None:
        try:
            async with self._session_factory() as session:
                event = AlertEvent(
                    inverter_id=inverter_id,
                    kind=kind,
                    title=title,
                    message=message,
                    started_at=tracker.started_at or now,
                    notified_at=now,
                    peak_value=tracker.peak,
                )
                session.add(event)
                await session.commit()
                return event.id
        except Exception:
            logger.exception("Could not store alert event")
            return None

    async def _mark_resolved(self, tracker: Tracker, now: datetime) -> None:
        if tracker.event_id is None:
            return
        try:
            async with self._session_factory() as session:
                await session.execute(
                    update(AlertEvent)
                    .where(AlertEvent.id == tracker.event_id)
                    .values(resolved_at=now, peak_value=tracker.peak)
                )
                await session.commit()
        except Exception:
            logger.exception("Could not update alert event")
        tracker.event_id = None

    async def _close_stale_events(self) -> None:
        """Alerts left open by a previous run are re-detected from scratch, so close them."""
        async with self._session_factory() as session:
            await session.execute(
                update(AlertEvent)
                .where(AlertEvent.resolved_at.is_(None))
                .values(resolved_at=self._clock())
            )
            await session.commit()

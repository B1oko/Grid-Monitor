"""Electricity cost estimates from stored samples and the user's tariffs.

The model follows the Spanish 2.0TD access tariff, which every supplier uses for
homes up to 15 kW:

- Energy bought from the grid is priced in three time periods: P1 (peak), P2
  (standard) and P3 (off-peak). Weekends and fixed-date national holidays are
  P3 all day.
- Contracted power is billed per kW and day in two periods (P1 and P2).
- Surplus exported to the grid is credited under simplified net billing: the
  credit can lower the energy term of a bill to zero, never below. Whatever is
  left over is lost (reported as ``surplus_lost_eur``).
- Electricity tax applies to power plus net energy. VAT applies to everything,
  electricity tax and fixed daily charges included.

Days take the tariff whose ``valid_from`` is the latest on or before that day.
Taxes for the whole range use the tariff in effect on its last day.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.db.models import Tariff

EnergyPeriod = Literal["p1", "p2", "p3"]
PERIODS: tuple[EnergyPeriod, ...] = ("p1", "p2", "p3")

# National holidays with a fixed date, which 2.0TD treats as off-peak all day.
FIXED_HOLIDAYS = {(1, 1), (1, 6), (5, 1), (8, 15), (10, 12), (11, 1), (12, 6), (12, 8), (12, 25)}

# Projections need at least a day of data to be meaningful.
MIN_PROJECTION_SPAN = timedelta(days=1)


def energy_period(local: datetime) -> EnergyPeriod:
    """2.0TD period for a local time: P1 10-14 and 18-22, P2 8-10, 14-18 and 22-24."""
    if local.weekday() >= 5 or (local.month, local.day) in FIXED_HOLIDAYS or local.hour < 8:
        return "p3"
    if 10 <= local.hour < 14 or 18 <= local.hour < 22:
        return "p1"
    return "p2"


def tariff_for(tariffs: Sequence[Tariff], day: date) -> Tariff | None:
    """Tariff in effect on ``day``; ``tariffs`` must be sorted by ``valid_from``."""
    current = None
    for tariff in tariffs:
        if tariff.valid_from > day:
            break
        current = tariff
    return current


def _energy_price(tariff: Tariff, period: EnergyPeriod) -> float:
    return getattr(tariff, f"energy_price_{period}")


def _daily_charges(tariff: Tariff) -> tuple[float, float]:
    power = (
        tariff.power_price_p1 * tariff.contracted_power_p1_kw
        + tariff.power_price_p2 * tariff.contracted_power_p2_kw
    )
    return power, tariff.fixed_daily


def _day_slices(start: datetime, end: datetime, tz: ZoneInfo) -> Iterator[tuple[date, float]]:
    """Local days overlapping ``[start, end)`` with the fraction of each day covered."""
    day = start.astimezone(tz).date()
    while True:
        day_start = datetime.combine(day, time(), tz)
        day_end = datetime.combine(day + timedelta(days=1), time(), tz)
        if day_start >= end:
            return
        covered = min(day_end, end) - max(day_start, start)
        if covered > timedelta(0):
            yield day, covered / (day_end - day_start)
        day += timedelta(days=1)


@dataclass
class _Day:
    import_kwh: dict[str, float] = field(default_factory=lambda: dict.fromkeys(PERIODS, 0.0))
    export_kwh: float = 0.0
    home_kwh: float = 0.0
    energy_eur: float = 0.0
    export_credit_eur: float = 0.0
    home_energy_eur: float = 0.0
    power_eur: float = 0.0
    fixed_eur: float = 0.0
    has_tariff: bool = False


def _bill(
    *,
    power: float,
    energy: float,
    export_credit: float,
    fixed: float,
    tariff: Tariff | None,
) -> dict[str, float]:
    compensation = min(export_credit, energy)
    tax_rate = tariff.electricity_tax_pct / 100 if tariff else 0.0
    vat_rate = tariff.vat_pct / 100 if tariff else 0.0
    electricity_tax = (power + energy - compensation) * tax_rate
    vat = (power + energy - compensation + electricity_tax + fixed) * vat_rate
    total = power + energy - compensation + fixed + electricity_tax + vat
    return {
        "power_eur": round(power, 2),
        "energy_eur": round(energy, 2),
        "compensation_eur": round(compensation, 2),
        "fixed_eur": round(fixed, 2),
        "electricity_tax_eur": round(electricity_tax, 2),
        "vat_eur": round(vat, 2),
        "total_eur": round(total, 2),
        "surplus_lost_eur": round(export_credit - compensation, 2),
    }


def estimate_costs(
    hours: Iterable[tuple[datetime, dict[str, float | None]]],
    tariffs: Iterable[Tariff],
    *,
    start: datetime,
    end: datetime,
    now: datetime,
    tz: ZoneInfo,
) -> dict[str, Any]:
    """Estimate the bill for ``[start, end)`` from hourly kWh (see ``hourly_energy``).

    Usage counts up to ``now``. When the range ends in the future, ``projected``
    extrapolates energy from the days so far and adds power and fixed charges for
    the whole range.
    """
    ordered = sorted(tariffs, key=lambda item: item.valid_from)
    used_end = max(start, min(end, now))
    days: dict[date, _Day] = {}

    for day, fraction in _day_slices(start, used_end, tz):
        entry = days.setdefault(day, _Day())
        tariff = tariff_for(ordered, day)
        if tariff is not None:
            power, fixed = _daily_charges(tariff)
            entry.power_eur += power * fraction
            entry.fixed_eur += fixed * fraction
            entry.has_tariff = True

    period_kwh = dict.fromkeys(PERIODS, 0.0)
    period_eur = dict.fromkeys(PERIODS, 0.0)
    for hour_start, values in hours:
        if not start <= hour_start < used_end:
            continue
        local = hour_start.astimezone(tz)
        period = energy_period(local)
        entry = days.setdefault(local.date(), _Day())
        imported = values.get("grid_import_kwh") or 0.0
        exported = values.get("grid_export_kwh") or 0.0
        home = values.get("home_kwh") or 0.0
        entry.import_kwh[period] += imported
        entry.export_kwh += exported
        entry.home_kwh += home
        period_kwh[period] += imported
        tariff = tariff_for(ordered, local.date())
        if tariff is None:
            continue
        price = _energy_price(tariff, period)
        entry.energy_eur += imported * price
        entry.export_credit_eur += exported * tariff.export_price
        entry.home_energy_eur += home * price
        period_eur[period] += imported * price

    def total(key: str) -> float:
        return sum(getattr(entry, key) for entry in days.values())

    last_day = (used_end - timedelta(microseconds=1)).astimezone(tz).date()
    tax_tariff = tariff_for(ordered, last_day)
    power, fixed = total("power_eur"), total("fixed_eur")
    totals = _bill(
        power=power,
        energy=total("energy_eur"),
        export_credit=total("export_credit_eur"),
        fixed=fixed,
        tariff=tax_tariff,
    )
    without_solar = _bill(
        power=power,
        energy=total("home_energy_eur"),
        export_credit=0.0,
        fixed=fixed,
        tariff=tax_tariff,
    )

    projected = None
    elapsed = used_end - start
    if end > now and elapsed >= MIN_PROJECTION_SPAN:
        factor = (end - start) / elapsed
        full_power = full_fixed = 0.0
        for day, fraction in _day_slices(start, end, tz):
            tariff = tariff_for(ordered, day)
            if tariff is not None:
                daily_power, daily_fixed = _daily_charges(tariff)
                full_power += daily_power * fraction
                full_fixed += daily_fixed * fraction
        projected = _bill(
            power=full_power,
            energy=total("energy_eur") * factor,
            export_credit=total("export_credit_eur") * factor,
            fixed=full_fixed,
            tariff=tariff_for(ordered, (end - timedelta(microseconds=1)).astimezone(tz).date()),
        )

    return {
        "has_tariff": any(entry.has_tariff for entry in days.values()),
        "missing_tariff_days": sum(1 for entry in days.values() if not entry.has_tariff),
        "totals": {
            **totals,
            "import_kwh": round(sum(period_kwh.values()), 3),
            "export_kwh": round(total("export_kwh"), 3),
            "home_kwh": round(total("home_kwh"), 3),
            "savings_eur": round(without_solar["total_eur"] - totals["total_eur"], 2),
        },
        "without_solar": without_solar,
        "projected": projected,
        "periods": {
            period: {
                "import_kwh": round(period_kwh[period], 3),
                "energy_eur": round(period_eur[period], 2),
            }
            for period in PERIODS
        },
        "days": [
            {
                "date": day.isoformat(),
                "import_kwh": {period: round(kwh, 3) for period, kwh in entry.import_kwh.items()},
                "export_kwh": round(entry.export_kwh, 3),
                "energy_eur": round(entry.energy_eur, 2) if entry.has_tariff else None,
                "export_credit_eur": round(entry.export_credit_eur, 2)
                if entry.has_tariff
                else None,
                "fixed_eur": round(entry.power_eur + entry.fixed_eur, 2)
                if entry.has_tariff
                else None,
            }
            for day, entry in sorted(days.items())
        ],
    }

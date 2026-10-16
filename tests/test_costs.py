from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.db.models import Tariff
from app.services.costs import energy_period, estimate_costs

MADRID = ZoneInfo("Europe/Madrid")


def _tariff(valid_from: date = date(2026, 1, 1), **overrides) -> Tariff:
    values = {
        "valid_from": valid_from,
        "energy_price_p1": 0.158,
        "energy_price_p2": 0.158,
        "energy_price_p3": 0.158,
        "power_price_p1": 0.097101,
        "power_price_p2": 0.029681,
        "contracted_power_p1_kw": 5.75,
        "contracted_power_p2_kw": 5.75,
        "export_price": 0.035,
        "fixed_daily": 0.0513,
        "electricity_tax_pct": 5.11,
        "vat_pct": 21.0,
    }
    return Tariff(**(values | overrides))


def _hour(local: datetime, **kwh: float) -> tuple[datetime, dict[str, float | None]]:
    return local.replace(tzinfo=MADRID).astimezone(UTC), kwh


def _range(start: datetime, end: datetime) -> dict:
    return {"start": start.replace(tzinfo=MADRID), "end": end.replace(tzinfo=MADRID), "tz": MADRID}


@pytest.mark.parametrize(
    ("local", "period"),
    [
        (datetime(2026, 9, 1, 7, 59), "p3"),
        (datetime(2026, 9, 1, 8, 0), "p2"),
        (datetime(2026, 9, 1, 10, 0), "p1"),
        (datetime(2026, 9, 1, 14, 30), "p2"),
        (datetime(2026, 9, 1, 19, 0), "p1"),
        (datetime(2026, 9, 1, 23, 0), "p2"),
        (datetime(2026, 9, 5, 12, 0), "p3"),  # Saturday
        (datetime(2026, 10, 12, 12, 0), "p3"),  # National holiday
    ],
)
def test_energy_period(local: datetime, period: str) -> None:
    assert energy_period(local) == period


def test_reproduces_a_real_bill() -> None:
    # Octopus Solar, September 2026: 96.60 EUR on the bill.
    hours = [
        _hour(datetime(2026, 9, 1, 11), grid_import_kwh=84.46),
        _hour(datetime(2026, 9, 1, 9), grid_import_kwh=117.06),
        _hour(datetime(2026, 9, 1, 3), grid_import_kwh=262.61),
        _hour(datetime(2026, 9, 1, 13), grid_export_kwh=590.96),
    ]
    result = estimate_costs(
        hours,
        [_tariff()],
        now=datetime(2026, 10, 5, tzinfo=UTC),
        **_range(datetime(2026, 9, 1), datetime(2026, 10, 1)),
    )

    totals = result["totals"]
    assert result["has_tariff"] is True
    assert result["projected"] is None
    assert totals["power_eur"] == pytest.approx(21.87, abs=0.01)
    assert totals["compensation_eur"] == pytest.approx(20.68, abs=0.01)
    assert totals["fixed_eur"] == pytest.approx(1.54, abs=0.01)
    assert totals["electricity_tax_eur"] == pytest.approx(3.81, abs=0.01)
    assert totals["total_eur"] == pytest.approx(96.60, abs=0.15)
    assert totals["surplus_lost_eur"] == 0
    assert result["periods"]["p1"]["import_kwh"] == pytest.approx(84.46)
    assert len(result["days"]) == 30


def test_compensation_never_exceeds_energy() -> None:
    hours = [
        _hour(datetime(2026, 7, 1, 3), grid_import_kwh=10, home_kwh=40),
        _hour(datetime(2026, 7, 1, 13), grid_export_kwh=100),
    ]
    tariff = _tariff(
        electricity_tax_pct=0, vat_pct=0, fixed_daily=0, power_price_p1=0, power_price_p2=0
    )
    result = estimate_costs(
        hours,
        [tariff],
        now=datetime(2026, 8, 1, tzinfo=UTC),
        **_range(datetime(2026, 7, 1), datetime(2026, 7, 2)),
    )

    totals = result["totals"]
    assert totals["energy_eur"] == pytest.approx(1.58)
    assert totals["compensation_eur"] == pytest.approx(1.58)
    assert totals["total_eur"] == 0
    assert totals["surplus_lost_eur"] == pytest.approx(3.5 - 1.58)
    assert result["without_solar"]["energy_eur"] == pytest.approx(6.32)
    assert totals["savings_eur"] == pytest.approx(6.32)


def test_each_day_uses_the_tariff_in_effect() -> None:
    cheap = _tariff(date(2026, 1, 1), energy_price_p3=0.10)
    dear = _tariff(date(2026, 3, 2), energy_price_p3=0.20)
    hours = [
        _hour(datetime(2026, 3, 1, 3), grid_import_kwh=1),
        _hour(datetime(2026, 3, 2, 3), grid_import_kwh=1),
    ]
    result = estimate_costs(
        hours,
        [dear, cheap],
        now=datetime(2026, 4, 1, tzinfo=UTC),
        **_range(datetime(2026, 2, 28), datetime(2026, 3, 3)),
    )

    assert [day["energy_eur"] for day in result["days"]] == [0, 0.10, 0.20]


def test_days_before_any_tariff_have_no_cost() -> None:
    result = estimate_costs(
        [_hour(datetime(2026, 3, 1, 3), grid_import_kwh=1)],
        [_tariff(date(2026, 3, 2))],
        now=datetime(2026, 4, 1, tzinfo=UTC),
        **_range(datetime(2026, 3, 1), datetime(2026, 3, 3)),
    )

    assert result["missing_tariff_days"] == 1
    assert result["days"][0]["energy_eur"] is None
    assert result["totals"]["energy_eur"] == 0


def test_projects_the_rest_of_the_period() -> None:
    hours = [_hour(datetime(2026, 9, day, 3), grid_import_kwh=10) for day in range(1, 11)]
    tariff = _tariff(electricity_tax_pct=0, vat_pct=0)
    result = estimate_costs(
        hours,
        [tariff],
        now=datetime(2026, 9, 11, tzinfo=MADRID),
        **_range(datetime(2026, 9, 1), datetime(2026, 10, 1)),
    )

    daily_power = 5.75 * (0.097101 + 0.029681)
    projected = result["projected"]
    assert len(result["days"]) == 10
    assert projected["energy_eur"] == pytest.approx(100 * 0.158 * 3, abs=0.01)
    assert projected["power_eur"] == pytest.approx(daily_power * 30, abs=0.01)
    assert result["totals"]["power_eur"] == pytest.approx(daily_power * 10, abs=0.01)


def test_no_projection_after_a_few_hours() -> None:
    result = estimate_costs(
        [],
        [_tariff()],
        now=datetime(2026, 9, 1, 5, tzinfo=MADRID),
        **_range(datetime(2026, 9, 1), datetime(2026, 10, 1)),
    )

    assert result["projected"] is None


TARIFF_BODY = {
    "valid_from": "2025-09-01",
    "energy_price_p1": 0.158,
    "energy_price_p2": 0.158,
    "energy_price_p3": 0.158,
    "power_price_p1": 0.097,
    "power_price_p2": 0.03,
    "contracted_power_p1_kw": 5.75,
    "contracted_power_p2_kw": 5.75,
}


def test_tariff_api(client: TestClient) -> None:
    created = client.post("/api/tariffs", json=TARIFF_BODY)
    assert created.status_code == 201
    tariff = created.json()
    assert tariff["vat_pct"] == 0
    assert client.post("/api/tariffs", json=TARIFF_BODY).status_code == 409

    updated = client.put(f"/api/tariffs/{tariff['id']}", json=TARIFF_BODY | {"vat_pct": 21})
    assert updated.status_code == 200
    assert updated.json()["vat_pct"] == 21
    assert [item["id"] for item in client.get("/api/tariffs").json()] == [tariff["id"]]

    assert client.delete(f"/api/tariffs/{tariff['id']}").status_code == 204
    assert client.get("/api/tariffs").json() == []


def test_costs_api(client: TestClient) -> None:
    inverter = client.post(
        "/api/inverters",
        json={"name": "Roof", "driver_id": "saj-h2", "host": "192.0.2.10"},
    ).json()
    params = {
        "inverter_id": inverter["id"],
        "from": "2025-09-01T00:00:00+02:00",
        "to": "2025-10-01T00:00:00+02:00",
        "tz": "Europe/Madrid",
    }

    empty = client.get("/api/costs", params=params)
    assert empty.status_code == 200
    assert empty.json()["has_tariff"] is False

    client.post("/api/tariffs", json=TARIFF_BODY)
    priced = client.get("/api/costs", params=params).json()
    assert priced["has_tariff"] is True
    assert priced["totals"]["power_eur"] == pytest.approx(5.75 * 0.127 * 30, abs=0.01)

    assert client.get("/api/costs", params=params | {"tz": "Mars/Base"}).status_code == 422
    backwards = params | {"from": params["to"], "to": params["from"]}
    assert client.get("/api/costs", params=backwards).status_code == 422

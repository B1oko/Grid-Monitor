"""Guards for the translation rules described in AGENTS.md."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.i18n import available_languages, catalog, placeholders, translate
from app.services.alerts import DEFAULT_RULES

STATIC = Path(__file__).resolve().parents[1] / "app" / "web" / "static"
SOURCES = sorted((STATIC / "js").rglob("*.js"))
REFERENCE = "en"


def frontend_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in SOURCES)


def test_reference_language_is_available() -> None:
    assert REFERENCE in available_languages()
    assert len(available_languages()) >= 2


@pytest.mark.parametrize("language", [lang for lang in available_languages() if lang != REFERENCE])
def test_locales_define_the_same_keys(language: str) -> None:
    reference, other = catalog(REFERENCE), catalog(language)
    missing = sorted(set(reference) - set(other))
    extra = sorted(set(other) - set(reference))
    assert not missing, f"{language}.json is missing keys: {missing}"
    assert not extra, f"{language}.json has keys not in {REFERENCE}.json: {extra}"


@pytest.mark.parametrize("language", [lang for lang in available_languages() if lang != REFERENCE])
def test_locales_use_the_same_placeholders(language: str) -> None:
    reference, other = catalog(REFERENCE), catalog(language)
    mismatched = {
        key: (sorted(placeholders(reference[key])), sorted(placeholders(other[key])))
        for key in reference
        if key in other and placeholders(reference[key]) != placeholders(other[key])
    }
    assert not mismatched, f"Placeholder mismatch in {language}.json: {mismatched}"


@pytest.mark.parametrize("language", available_languages())
def test_locales_have_no_empty_strings(language: str) -> None:
    empty = [key for key, value in catalog(language).items() if not value.strip()]
    assert not empty, f"Empty strings in {language}.json: {empty}"


def test_frontend_keys_exist() -> None:
    keys = set(catalog(REFERENCE))
    source = frontend_source()
    missing: list[str] = []

    for literal in re.findall(r"\bt\(\s*([\"'`])(.+?)\1", source):
        key = literal[1]
        if "${" in key:
            pattern = re.compile("^" + re.sub(r"\\\$\\\{[^}]+\\\}", r"[^.]+", re.escape(key)) + "$")
            if not any(pattern.match(k) for k in keys):
                missing.append(key)
        elif key not in keys:
            missing.append(key)

    # Keys kept in constants and passed to t() later, e.g. chart series labels.
    namespaces = {key.split(".")[0] for key in keys}
    for literal in re.findall(r"[\"']([a-z_]+(?:\.[a-z0-9_]+)+)[\"']", source):
        if literal.split(".")[0] in namespaces and literal not in keys:
            missing.append(literal)

    assert not missing, (
        f"Keys used in the web UI but missing from {REFERENCE}.json: {sorted(set(missing))}"
    )


def test_backend_alert_keys_exist() -> None:
    keys = set(catalog(REFERENCE))
    required = {"push.test.title", "push.test.body"}
    for rule in DEFAULT_RULES:
        for suffix in (
            "name",
            "description",
            "fire.title",
            "fire.body",
            "resolve.title",
            "resolve.body",
        ):
            required.add(f"alerts.{rule.kind}.{suffix}")
    assert required <= keys, sorted(required - keys)


def test_locale_files_are_valid_json_objects() -> None:
    for language in available_languages():
        data = json.loads((Path("app/i18n/locales") / f"{language}.json").read_text("utf-8"))
        assert isinstance(data, dict)
        assert data["meta"]["language_name"]


def test_translate_formats_by_placeholder_suffix() -> None:
    params = {"inverter": "Roof", "peak_w": 6200.4, "limit_w": 5500, "duration_min": 75}
    assert translate("alerts.overload.fire.body", "en", **params) == (
        "Roof: importing 6,200 W from the grid (limit 5,500 W) for 1 h 15 min."
    )
    spanish = translate("alerts.overload.fire.body", "es-ES", **params)
    assert "6.200 W" in spanish and "5.500 W" in spanish and "1 h 15 min" in spanish


def test_translate_falls_back_to_reference_language() -> None:
    assert translate("nav.alerts", "xx") == catalog(REFERENCE)["nav.alerts"]
    assert translate("does.not.exist", "es") == "does.not.exist"


def test_service_worker_precaches_every_module() -> None:
    sw = (STATIC / "sw.js").read_text(encoding="utf-8")
    missing = [
        f"/static/{path.relative_to(STATIC).as_posix()}"
        for path in SOURCES
        if f'"/static/{path.relative_to(STATIC).as_posix()}"' not in sw
    ]
    assert not missing, f"Add these files to PRECACHE in sw.js: {missing}"

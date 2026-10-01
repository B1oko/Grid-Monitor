"""Translations shared by the backend (push notifications) and the web UI.

Every user-facing string lives in ``locales/<lang>.json``. ``en.json`` is the
reference catalog: other languages must define exactly the same keys and
placeholders (enforced by ``tests/test_i18n.py``).

Placeholders use ``{name}``. The suffix of the name picks the formatting, so a
template stays language-neutral and values are stored raw:

- ``*_w``   -> power, e.g. ``6,200 W``
- ``*_min`` -> duration from minutes, e.g. ``1 h 05 min``
- ``*_deg`` -> angle, e.g. ``15°``
- anything else is inserted as-is.

The web UI implements the same rules in ``app/web/static/js/i18n.js``.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LANGUAGE = "en"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _flatten(prefix: str, value: Any, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _flatten(f"{prefix}.{key}" if prefix else key, child, out)
    else:
        out[prefix] = str(value)


@lru_cache
def available_languages() -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in LOCALES_DIR.glob("*.json")))


@lru_cache
def catalog(language: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{language}.json"
    out: dict[str, str] = {}
    _flatten("", json.loads(path.read_text(encoding="utf-8")), out)
    return out


def normalize_language(value: str | None) -> str:
    """Map a browser tag such as ``es-ES`` to a supported language code."""
    if value:
        code = value.strip().lower().replace("_", "-").split("-")[0]
        if code in available_languages():
            return code
    return DEFAULT_LANGUAGE


def format_number(value: float, language: str, decimals: int = 0) -> str:
    meta = catalog(language)
    thousands = meta.get("meta.thousands_separator", ",")
    decimal = meta.get("meta.decimal_separator", ".")
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\0").replace(".", decimal).replace("\0", thousands)


def format_duration(minutes: float) -> str:
    total = max(0, round(minutes))
    if total < 60:
        return f"{total} min"
    return f"{total // 60} h {total % 60:02d} min"


def format_param(name: str, value: Any, language: str) -> str:
    if value is None:
        return "--"
    if name.endswith("_w"):
        return f"{format_number(float(value), language)} W"
    if name.endswith("_min"):
        return format_duration(float(value))
    if name.endswith("_deg"):
        return f"{round(float(value))}°"
    return str(value)


def render(template: str, language: str, params: dict[str, Any] | None = None) -> str:
    params = params or {}

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in params:
            return match.group(0)
        return format_param(name, params[name], language)

    return _PLACEHOLDER.sub(replace, template)


def translate(key: str, language: str = DEFAULT_LANGUAGE, **params: Any) -> str:
    language = normalize_language(language)
    template = catalog(language).get(key) or catalog(DEFAULT_LANGUAGE).get(key) or key
    return render(template, language, params)


def placeholders(template: str) -> set[str]:
    return set(_PLACEHOLDER.findall(template))

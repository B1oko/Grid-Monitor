"""Check and print the app version.

``pyproject.toml`` is the source of truth. ``app/__init__.py`` must match it and
``CHANGELOG.md`` must start with a section for it. Every pull request raises the
version, which CI checks with ``--base`` against the target branch.

Usage:
    python scripts/version.py                      # check consistency
    python scripts/version.py --base OLD.toml      # also require a higher version
    python scripts/version.py --print              # print the version
    python scripts/version.py --notes              # print its CHANGELOG section

Only the standard library is used, so CI can run it without installing anything.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
APP_VERSION = re.compile(r'^__version__ = "([^"]+)"$', re.MULTILINE)
CHANGELOG_HEADING = re.compile(r"^## \[([^\]]+)\](?: - (\d{4}-\d{2}-\d{2}))?$", re.MULTILINE)


def parse(version: str) -> tuple[int, int, int]:
    match = SEMVER.match(version)
    if not match:
        raise ValueError(f"{version!r} is not MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def pyproject_version(path: Path) -> str:
    return tomllib.loads(path.read_text(encoding="utf-8"))["project"]["version"]


def changelog_section(text: str) -> tuple[str, str | None, str]:
    """First version heading of the changelog, its date and its body."""
    headings = list(CHANGELOG_HEADING.finditer(text))
    if not headings:
        raise ValueError("CHANGELOG.md has no '## [x.y.z] - YYYY-MM-DD' section")
    first = headings[0]
    end = headings[1].start() if len(headings) > 1 else len(text)
    return first.group(1), first.group(2), text[first.end() : end].strip()


def problems(root: Path = ROOT, base: str | None = None) -> list[str]:
    version = pyproject_version(root / "pyproject.toml")
    errors = []
    try:
        parse(version)
    except ValueError as exc:
        return [f"pyproject.toml: {exc}"]

    app = APP_VERSION.search((root / "app" / "__init__.py").read_text(encoding="utf-8"))
    if not app or app.group(1) != version:
        found = app.group(1) if app else "nothing"
        errors.append(f"app/__init__.py has {found}, pyproject.toml has {version}")

    try:
        heading, released, _ = changelog_section(
            (root / "CHANGELOG.md").read_text(encoding="utf-8")
        )
        if heading != version or not released:
            errors.append(
                f"CHANGELOG.md must start with '## [{version}] - YYYY-MM-DD', "
                f"found '## [{heading}]'"
            )
    except ValueError as exc:
        errors.append(str(exc))

    if base is not None and parse(version) <= parse(base):
        errors.append(f"version {version} must be higher than {base} on the target branch")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", type=Path, help="pyproject.toml of the target branch")
    parser.add_argument("--print", action="store_true", help="print the version")
    parser.add_argument("--notes", action="store_true", help="print its CHANGELOG section")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    if args.print:
        print(pyproject_version(ROOT / "pyproject.toml"))
        return 0
    if args.notes:
        print(changelog_section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))[2])
        return 0

    base = pyproject_version(args.base) if args.base else None
    errors = problems(base=base)
    for error in errors:
        print(f"::error::{error}")
    if not errors:
        print(f"Version {pyproject_version(ROOT / 'pyproject.toml')} OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

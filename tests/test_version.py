import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import __version__
from scripts.version import ROOT, changelog_section, parse, problems


def _copy(tmp_path: Path) -> Path:
    for name in ("pyproject.toml", "CHANGELOG.md"):
        shutil.copy(ROOT / name, tmp_path / name)
    (tmp_path / "app").mkdir()
    shutil.copy(ROOT / "app" / "__init__.py", tmp_path / "app" / "__init__.py")
    return tmp_path


def test_repository_version_is_consistent() -> None:
    assert problems() == []


def test_version_must_be_higher_than_the_target_branch() -> None:
    major, minor, patch = parse(__version__)
    assert problems(base=f"{major}.{minor}.{patch + 1}")
    assert problems(base=__version__)
    assert problems(base="0.0.0") == []


def test_app_version_must_match_pyproject(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    init = root / "app" / "__init__.py"
    init.write_text(init.read_text().replace(__version__, "9.9.9"))
    assert any("app/__init__.py" in error for error in problems(root))


def test_changelog_must_start_with_the_version(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    changelog = root / "CHANGELOG.md"
    changelog.write_text(changelog.read_text().replace(f"## [{__version__}]", "## [Unreleased]", 1))
    assert any("CHANGELOG.md" in error for error in problems(root))


def test_changelog_section_returns_the_newest_notes() -> None:
    version, date, notes = changelog_section(
        "# Changelog\n\n## [1.1.0] - 2026-10-16\n\n- New\n\n## [1.0.0] - 2026-01-01\n\n- Old\n"
    )
    assert (version, date, notes) == ("1.1.0", "2026-10-16", "- New")


@pytest.mark.parametrize("value", ["1.2", "v1.2.3", "1.2.3-rc1"])
def test_rejects_non_semver(value: str) -> None:
    with pytest.raises(ValueError):
        parse(value)


def test_service_worker_cache_follows_the_version(client: TestClient) -> None:
    script = client.get("/sw.js").text
    assert f'const CACHE = "grid-monitor-{__version__}";' in script
    assert "__VERSION__" not in script

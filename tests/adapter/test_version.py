"""Version reporting: package metadata is the single source of truth."""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

import para_quest_notes
from para_quest_notes.adapter.cli import build_base_parser

REPO_ROOT = Path(__file__).resolve().parents[2]


def _declared_version() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        version: str = tomllib.load(fh)["project"]["version"]
    return version


def _console_scripts() -> list[str]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        scripts: dict[str, str] = tomllib.load(fh)["project"]["scripts"]
    return sorted(scripts)


def test_version_matches_pyproject() -> None:
    """The runtime version comes from metadata, so it tracks pyproject.toml."""
    assert para_quest_notes.__version__ == _declared_version()


def test_version_is_not_a_placeholder() -> None:
    """Guard against the hardcoded 0.0.1 that used to drift from pyproject."""
    assert para_quest_notes.__version__ not in {"0.0.1", "0+unknown"}


def test_base_parser_version_flag_exits_zero_and_prints_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    parser = build_base_parser(prog="pqn-example", description="Example.")

    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--version"])

    assert excinfo.value.code == 0
    out = capsys.readouterr().out.strip()
    assert out == f"pqn-example {para_quest_notes.__version__}"


@pytest.mark.parametrize("script", _console_scripts())
def test_every_entry_point_reports_version(script: str) -> None:
    """Every installed command answers --version with the same version."""
    proc = subprocess.run(
        [script, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""
    # prog differs per command; the version is what must agree.
    assert proc.stdout.strip().endswith(f" {para_quest_notes.__version__}")

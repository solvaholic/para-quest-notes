"""Strict configuration tests for ``pqn-daily``."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import ConfigError
from para_quest_notes.workflows.daily.settings import resolve_daily_settings


def test_daily_settings_default_to_safe_disabled_values() -> None:
    settings = resolve_daily_settings({})

    assert settings.create_missing is False
    assert settings.open_existing is False
    assert settings.editor is None


def test_daily_settings_load_valid_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "workflows:\n"
        "  daily:\n"
        "    create_missing: true\n"
        "    open_existing: true\n"
        "    editor: [code, --reuse-window]\n",
        encoding="utf-8",
    )

    settings = resolve_daily_settings(load_config(config_path).workflows)

    assert settings.create_missing is True
    assert settings.open_existing is True
    assert settings.editor == ("code", "--reuse-window")


@pytest.mark.parametrize(
    ("daily", "key"),
    [
        ("[]", "workflows.daily"),
        ("{create_missing: 'true'}", "workflows.daily.create_missing"),
        ("{open_existing: 1}", "workflows.daily.open_existing"),
        ("{editor: []}", "workflows.daily.editor"),
        ("{editor: code}", "workflows.daily.editor"),
        ("{editor: [code, 1]}", "workflows.daily.editor[1]"),
        ("{editor: ['']}", "workflows.daily.editor[0]"),
    ],
)
def test_malformed_daily_settings_name_exact_key(daily: str, key: str, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"workflows:\n  daily: {daily}\n", encoding="utf-8")

    with pytest.raises(ConfigError, match=key.replace("[", r"\[").replace("]", r"\]")):
        resolve_daily_settings(load_config(config_path).workflows)

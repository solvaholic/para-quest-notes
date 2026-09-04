"""Strict ``workflows.daily`` configuration parsing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from para_quest_notes.adapter.errors import ConfigError


@dataclass(frozen=True)
class DailySettings:
    create_missing: bool = False
    open_existing: bool = False
    editor: tuple[str, ...] | None = None


def resolve_daily_settings(workflows: Mapping[str, Any]) -> DailySettings:
    """Return validated daily settings with safe defaults."""
    if "daily" not in workflows:
        return DailySettings()

    raw = workflows["daily"]
    if not isinstance(raw, Mapping):
        raise ConfigError("workflows.daily must be a mapping")

    create_missing = _boolean(raw, "create_missing", default=False)
    open_existing = _boolean(raw, "open_existing", default=False)
    editor = _editor(raw)
    return DailySettings(
        create_missing=create_missing,
        open_existing=open_existing,
        editor=editor,
    )


def _boolean(raw: Mapping[str, Any], key: str, *, default: bool) -> bool:
    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, bool):
        raise ConfigError(f"workflows.daily.{key} must be a boolean")
    return value


def _editor(raw: Mapping[str, Any]) -> tuple[str, ...] | None:
    if "editor" not in raw:
        return None
    value = raw["editor"]
    if not isinstance(value, list) or not value:
        raise ConfigError("workflows.daily.editor must be a non-empty argv list")
    for index, argument in enumerate(value):
        if not isinstance(argument, str) or not argument:
            raise ConfigError(f"workflows.daily.editor[{index}] must be a non-empty string")
    return tuple(value)

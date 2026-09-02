"""Resolve ``pqn-tasks`` workflow settings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from para_quest_notes.adapter.errors import ConfigError

from .contract import DATE_FIELDS


def configured_date_fields(workflows: Mapping[str, Any]) -> list[str] | None:
    """Return validated ``workflows.tasks.date_fields``, when configured."""
    if "tasks" not in workflows:
        return None
    tasks_config = workflows["tasks"]
    if not isinstance(tasks_config, Mapping):
        raise ConfigError("workflows.tasks must be a mapping")

    if "date_fields" not in tasks_config:
        return None
    raw = tasks_config["date_fields"]
    if not isinstance(raw, list) or not raw:
        raise ConfigError("workflows.tasks.date_fields must be a non-empty list")

    invalid = [value for value in raw if not isinstance(value, str) or value not in DATE_FIELDS]
    if invalid:
        allowed = ", ".join(DATE_FIELDS)
        raise ConfigError(
            f"workflows.tasks.date_fields entries must be one of: {allowed}; got {invalid!r}"
        )
    return list(raw)


def resolve_date_fields(
    cli_value: Sequence[str] | None,
    workflows: Mapping[str, Any],
) -> list[str]:
    """Resolve date precedence as flag, then config, then built-in default."""
    configured = configured_date_fields(workflows)
    if cli_value is not None:
        return list(cli_value)
    return configured or list(DATE_FIELDS)

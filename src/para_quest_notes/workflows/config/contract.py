"""Public JSON contract for ``pqn-config`` output.

Stable across releases — agents and humans both consume this. Add fields
rather than rename. Every configurable value is reported as a
:class:`Setting` so its provenance travels with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Where a reported value came from. ``default`` = built-in constant,
# ``config`` = a key set in config.yaml, ``env`` = environment variable,
# ``flag`` = a command-line flag. Vault resolution additionally uses
# ``cwd`` (see VaultInfo.source).
Source = Literal["default", "config", "env", "flag", "cwd"]

# The sections a caller can isolate with ``--section``. Omitting the flag
# reports every section.
SECTIONS = ("vault", "models", "ollama", "tasks", "templates", "paths")


@dataclass
class Setting:
    """One configurable value plus the layer that produced it."""

    value: Any
    source: Source

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "source": self.source}


@dataclass
class HonoredSetting(Setting):
    """A workflow setting plus whether that workflow consumes it."""

    honored: bool

    def to_dict(self) -> dict[str, Any]:
        return {**super().to_dict(), "honored": self.honored}


@dataclass
class VaultInfo:
    """Resolved vault path and which discovery rung won.

    ``resolved`` is ``False`` when no vault could be found; ``path`` and
    ``source`` are then ``None`` and ``error`` carries the reason. Unlike
    the write CLIs, ``pqn-config`` reports an unresolved vault rather than
    failing — inspecting config shouldn't require a vault.
    """

    resolved: bool
    path: str | None = None
    source: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolved": self.resolved,
            "path": self.path,
            "source": self.source,
            "error": self.error,
        }


@dataclass
class ModelOverride:
    """A per-workflow ``workflows.<name>.model`` setting.

    ``honored`` reports whether the workflow actually reads the override.
    Today no workflow does (they resolve ``args.model or
    config.ollama.default_model``), so this surfaces documented-but-unwired
    drift instead of hiding it.
    """

    workflow: str
    model: str
    honored: bool

    def to_dict(self) -> dict[str, Any]:
        return {"workflow": self.workflow, "model": self.model, "honored": self.honored}


@dataclass
class ModelsInfo:
    default_model: Setting
    overrides: list[ModelOverride] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "default_model": self.default_model.to_dict(),
            "overrides": [o.to_dict() for o in self.overrides],
        }


@dataclass
class OllamaInfo:
    base_url: Setting
    request_timeout_seconds: Setting

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url.to_dict(),
            "request_timeout_seconds": self.request_timeout_seconds.to_dict(),
        }


@dataclass
class TasksInfo:
    date_fields: HonoredSetting

    def to_dict(self) -> dict[str, Any]:
        return {"date_fields": self.date_fields.to_dict()}


@dataclass
class TemplatesInfo:
    """Template dir, per-type defaults, and (when the vault resolves) the
    template files found on disk. ``files`` is ``None`` when the vault is
    unresolved or the template dir doesn't exist — distinct from ``[]``
    (dir exists, no templates)."""

    template_dir: Setting
    defaults: dict[str, str] = field(default_factory=dict)
    files: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_dir": self.template_dir.to_dict(),
            "defaults": dict(self.defaults),
            "files": None if self.files is None else list(self.files),
        }


@dataclass
class PathsInfo:
    """Filesystem locations. ``run_log_dir`` is the effective base for run
    traces; ``source_path`` is the config file that was loaded (reported
    even when it doesn't exist, alongside ``config_found``)."""

    run_log_dir: Setting
    source_path: str
    config_found: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_log_dir": self.run_log_dir.to_dict(),
            "source_path": self.source_path,
            "config_found": self.config_found,
        }


@dataclass
class ConfigReport:
    """Top-level result ``pqn-config`` emits."""

    vault: VaultInfo
    models: ModelsInfo
    ollama: OllamaInfo
    tasks: TasksInfo
    templates: TemplatesInfo
    paths: PathsInfo

    def to_dict(self, section: str | None = None) -> dict[str, Any]:
        all_sections = {
            "vault": self.vault.to_dict(),
            "models": self.models.to_dict(),
            "ollama": self.ollama.to_dict(),
            "tasks": self.tasks.to_dict(),
            "templates": self.templates.to_dict(),
            "paths": self.paths.to_dict(),
        }
        if section is None:
            return all_sections
        return {section: all_sections[section]}

"""Build the effective-config report for ``pqn-config``.

Values come from the already-loaded :class:`Config` (the authority on what
a run uses). Provenance — the *source* label on each value — is derived by
re-reading the raw ``config.yaml`` mapping to see which keys were actually
present, so "config" vs "default" is exact rather than guessed from
whether a value happens to equal its default.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.errors import VaultError
from para_quest_notes.adapter.trace import default_state_dir
from para_quest_notes.adapter.vault import resolve_vault
from para_quest_notes.workflows.create.templates import get_template_config
from para_quest_notes.workflows.tasks.settings import resolve_date_fields

from .contract import (
    ConfigReport,
    HonoredSetting,
    ModelOverride,
    ModelsInfo,
    OllamaInfo,
    PathsInfo,
    Setting,
    Source,
    TasksInfo,
    TemplatesInfo,
    VaultInfo,
)

# Workflows that actually read their ``workflows.<name>.model`` override.
# Empty today: every LLM workflow resolves ``args.model or
# config.ollama.default_model`` and ignores the per-workflow key. When a
# workflow is wired to honor it, add its name here so pqn-config reports
# ``honored: true``.
_MODEL_OVERRIDE_HONORED: frozenset[str] = frozenset()


def _load_raw(path: Path | None) -> dict[str, Any]:
    """Return the raw top-level mapping from ``config.yaml``, or ``{}``.

    Presence of keys drives provenance labels only; :func:`load_config` has
    already validated shape and owns the values, so any parse hiccup here
    degrades gracefully to "everything is a default".
    """
    if path is None or not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return {}
    return raw if isinstance(raw, dict) else {}


def _present(raw: Mapping[str, Any], *keys: str) -> bool:
    """True if the nested key path exists (and isn't null) in ``raw``."""
    node: Any = raw
    for key in keys:
        if not isinstance(node, Mapping) or node.get(key) is None:
            return False
        node = node[key]
    return True


def _source(raw: Mapping[str, Any], *keys: str) -> Source:
    return "config" if _present(raw, *keys) else "default"


def inspect_config(
    *,
    config: Config,
    vault_arg: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    start_dir: Path | None = None,
) -> ConfigReport:
    """Assemble the full :class:`ConfigReport` from a loaded config."""
    raw = _load_raw(config.source_path)

    vault_info, vault_path = _inspect_vault(config, vault_arg, env, start_dir)
    template_dir, defaults = get_template_config(config.workflows)

    return ConfigReport(
        vault=vault_info,
        models=_inspect_models(config, raw),
        ollama=_inspect_ollama(config, raw),
        tasks=_inspect_tasks(config, raw),
        templates=_inspect_templates(config, raw, template_dir, defaults, vault_path),
        paths=_inspect_paths(config, raw),
    )


def _inspect_vault(
    config: Config,
    vault_arg: str | os.PathLike[str] | None,
    env: Mapping[str, str] | None,
    start_dir: Path | None,
) -> tuple[VaultInfo, Path | None]:
    try:
        path, source = resolve_vault(vault_arg, env=env, start_dir=start_dir, config=config)
    except VaultError as exc:
        return VaultInfo(resolved=False, error=str(exc)), None
    return VaultInfo(resolved=True, path=str(path), source=source), path


def _inspect_models(config: Config, raw: Mapping[str, Any]) -> ModelsInfo:
    default_model = Setting(
        value=config.ollama.default_model,
        source=_source(raw, "ollama", "default_model"),
    )
    overrides: list[ModelOverride] = []
    for name, wf in config.workflows.items():
        if isinstance(wf, Mapping) and wf.get("model") is not None:
            overrides.append(
                ModelOverride(
                    workflow=str(name),
                    model=str(wf["model"]),
                    honored=str(name) in _MODEL_OVERRIDE_HONORED,
                )
            )
    overrides.sort(key=lambda o: o.workflow)
    return ModelsInfo(default_model=default_model, overrides=overrides)


def _inspect_ollama(config: Config, raw: Mapping[str, Any]) -> OllamaInfo:
    return OllamaInfo(
        base_url=Setting(
            value=config.ollama.base_url,
            source=_source(raw, "ollama", "base_url"),
        ),
        request_timeout_seconds=Setting(
            value=config.ollama.request_timeout_seconds,
            source=_source(raw, "ollama", "request_timeout_seconds"),
        ),
    )


def _inspect_tasks(config: Config, raw: Mapping[str, Any]) -> TasksInfo:
    return TasksInfo(
        date_fields=HonoredSetting(
            value=resolve_date_fields(None, config.workflows),
            source=_source(raw, "workflows", "tasks", "date_fields"),
            honored=True,
        )
    )


def _inspect_templates(
    config: Config,
    raw: Mapping[str, Any],
    template_dir: str,
    defaults: dict[str, str],
    vault_path: Path | None,
) -> TemplatesInfo:
    return TemplatesInfo(
        template_dir=Setting(
            value=template_dir,
            source=_source(raw, "workflows", "create", "template_dir"),
        ),
        defaults=defaults,
        files=_list_template_files(vault_path, template_dir),
    )


def _list_template_files(vault_path: Path | None, template_dir: str) -> list[str] | None:
    """Sorted basenames of ``*.md`` under the template dir, or ``None``.

    ``None`` means the vault is unresolved or the template dir is absent —
    kept distinct from ``[]`` (dir present but empty).
    """
    if vault_path is None:
        return None
    tdir = vault_path / template_dir
    if not tdir.is_dir():
        return None
    return sorted(p.name for p in tdir.glob("*.md") if p.is_file())


def _inspect_paths(config: Config, raw: Mapping[str, Any]) -> PathsInfo:
    if config.run_log_dir is not None:
        run_log = Setting(value=str(config.run_log_dir), source="config")
    else:
        run_log = Setting(value=str(default_state_dir()), source="default")
    source_path = config.source_path
    return PathsInfo(
        run_log_dir=run_log,
        source_path="" if source_path is None else str(source_path),
        config_found=source_path is not None and source_path.exists(),
    )

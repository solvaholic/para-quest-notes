"""Tool-config loader.

Lives at ``$XDG_CONFIG_HOME/para-quest-notes/config.yaml`` (falls back to
``~/.config/para-quest-notes/config.yaml``). An empty or missing file is
fine - sensible defaults apply.

See ``docs/configuration.md`` for the user-facing shape.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from para_quest_notes.adapter.errors import ConfigError

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "granite4.1:30b"
DEFAULT_OLLAMA_TIMEOUT_S = 120


@dataclass
class OllamaConfig:
    base_url: str = DEFAULT_OLLAMA_BASE_URL
    default_model: str = DEFAULT_OLLAMA_MODEL
    request_timeout_seconds: int = DEFAULT_OLLAMA_TIMEOUT_S


@dataclass
class Config:
    """In-memory tool config.

    ``vault`` is optional here - vault resolution is layered (see
    ``vault.find_vault``); the config is only one rung in that ladder.
    """

    vault: Path | None = None
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    workflows: dict[str, dict[str, Any]] = field(default_factory=dict)
    run_log_dir: Path | None = None
    source_path: Path | None = None


def default_config_path() -> Path:
    """XDG-respecting default location of ``config.yaml``."""
    base = os.environ.get("XDG_CONFIG_HOME")
    base_path = Path(base) if base else Path.home() / ".config"
    return base_path / "para-quest-notes" / "config.yaml"


def _expand(value: str | os.PathLike[str]) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(value))))


def load_config(path: Path | None = None) -> Config:
    """Load config from ``path`` (or the XDG default).

    Missing file is fine. Empty file is fine. Anything that isn't a mapping
    at the top level is a ``ConfigError`` - we want loud failure on shape
    mistakes so users notice typos early.
    """
    cfg_path = path or default_config_path()

    if not cfg_path.exists():
        return Config(source_path=cfg_path)

    try:
        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"failed to parse {cfg_path}: {exc}") from exc

    if raw is None:
        return Config(source_path=cfg_path)
    if not isinstance(raw, dict):
        raise ConfigError(f"{cfg_path}: top level must be a mapping, got {type(raw).__name__}")

    cfg = Config(source_path=cfg_path)

    if "vault" in raw and raw["vault"] is not None:
        cfg.vault = _expand(raw["vault"])

    if "ollama" in raw and raw["ollama"] is not None:
        ollama_raw = raw["ollama"]
        if not isinstance(ollama_raw, dict):
            raise ConfigError(f"{cfg_path}: 'ollama' must be a mapping")
        cfg.ollama = OllamaConfig(
            base_url=str(ollama_raw.get("base_url", DEFAULT_OLLAMA_BASE_URL)),
            default_model=str(ollama_raw.get("default_model", DEFAULT_OLLAMA_MODEL)),
            request_timeout_seconds=int(
                ollama_raw.get("request_timeout_seconds", DEFAULT_OLLAMA_TIMEOUT_S)
            ),
        )

    if "workflows" in raw and raw["workflows"] is not None:
        wf = raw["workflows"]
        if not isinstance(wf, dict):
            raise ConfigError(f"{cfg_path}: 'workflows' must be a mapping")
        cfg.workflows = wf

    if "run_log_dir" in raw and raw["run_log_dir"] is not None:
        cfg.run_log_dir = _expand(raw["run_log_dir"])

    return cfg

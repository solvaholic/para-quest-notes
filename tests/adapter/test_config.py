"""Tests for adapter.config."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.adapter.config import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    Config,
    default_config_path,
    load_config,
)
from para_quest_notes.adapter.errors import ConfigError


def test_missing_file_returns_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nope.yaml")
    assert isinstance(cfg, Config)
    assert cfg.vault is None
    assert cfg.ollama.base_url == DEFAULT_OLLAMA_BASE_URL
    assert cfg.ollama.default_model == DEFAULT_OLLAMA_MODEL
    assert cfg.workflows == {}


def test_empty_file_returns_defaults(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("")
    cfg = load_config(p)
    assert cfg.vault is None
    assert cfg.ollama.default_model == DEFAULT_OLLAMA_MODEL


def test_partial_override_merges(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text(
        "vault: ~/notes\n"
        "ollama:\n"
        "  default_model: qwen3:30b\n"
        "workflows:\n"
        "  ingest:\n"
        "    temperature: 0.2\n"
    )
    cfg = load_config(p)
    assert cfg.vault is not None and cfg.vault.is_absolute()
    assert cfg.ollama.default_model == "qwen3:30b"
    # base_url + timeout should still be defaults.
    assert cfg.ollama.base_url == DEFAULT_OLLAMA_BASE_URL
    assert cfg.workflows["ingest"]["temperature"] == 0.2


def test_xdg_config_home_honored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    expected = tmp_path / "para-quest-notes" / "config.yaml"
    assert default_config_path() == expected


def test_falls_back_to_home_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    p = default_config_path()
    assert p.parts[-2:] == ("para-quest-notes", "config.yaml")
    assert ".config" in p.parts


def test_top_level_must_be_mapping(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("- just\n- a\n- list\n")
    with pytest.raises(ConfigError):
        load_config(p)


def test_invalid_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "config.yaml"
    p.write_text("vault: ~/notes\n  bad: indent\n")
    with pytest.raises(ConfigError):
        load_config(p)

"""Tests for adapter.vault."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.errors import VaultError
from para_quest_notes.adapter.vault import VAULT_ENV_VAR, find_vault, is_vault, resolve_vault


def make_vault(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "areas").mkdir()
    (root / "projects").mkdir()
    return root


def test_is_vault_requires_both_markers(tmp_path: Path) -> None:
    (tmp_path / "areas").mkdir()
    assert not is_vault(tmp_path)
    (tmp_path / "projects").mkdir()
    assert is_vault(tmp_path)


def test_arg_wins(tmp_path: Path) -> None:
    v = make_vault(tmp_path / "v")
    assert find_vault(arg=str(v), env={}, start_dir=tmp_path) == v.resolve()


def test_arg_must_exist(tmp_path: Path) -> None:
    with pytest.raises(VaultError):
        find_vault(arg=str(tmp_path / "nope"), env={}, start_dir=tmp_path)


def test_env_var(tmp_path: Path) -> None:
    v = make_vault(tmp_path / "v")
    assert find_vault(env={VAULT_ENV_VAR: str(v)}, start_dir=tmp_path) == v.resolve()


def test_walk_up_from_subdir(tmp_path: Path) -> None:
    v = make_vault(tmp_path / "v")
    inner = v / "areas" / "deep" / "deeper"
    inner.mkdir(parents=True)
    assert find_vault(env={}, start_dir=inner) == v.resolve()


def test_config_fallback(tmp_path: Path) -> None:
    v = make_vault(tmp_path / "v")
    cfg = Config(vault=v)
    other = tmp_path / "elsewhere"
    other.mkdir()
    assert find_vault(env={}, start_dir=other, config=cfg) == v.resolve()


def test_helpful_error_when_unresolvable(tmp_path: Path) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    with pytest.raises(VaultError) as exc:
        find_vault(env={}, start_dir=other)
    msg = str(exc.value)
    assert "--vault" in msg
    assert VAULT_ENV_VAR in msg


def test_resolve_vault_reports_winning_rung(tmp_path: Path) -> None:
    v = make_vault(tmp_path / "v")
    other = tmp_path / "elsewhere"
    other.mkdir()

    assert resolve_vault(v, env={}, start_dir=other) == (v.resolve(), "flag")
    assert resolve_vault(env={VAULT_ENV_VAR: str(v)}, start_dir=other) == (v.resolve(), "env")
    assert resolve_vault(env={}, start_dir=v / "areas") == (v.resolve(), "cwd")
    assert resolve_vault(env={}, start_dir=other, config=Config(vault=v)) == (v.resolve(), "config")

"""Tests for the ``--quest-kind`` flag and its deprecated ``--quest`` alias (#98)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from para_quest_notes.vault.frontmatter import LegacyQuestKeyWarning
from para_quest_notes.workflows.create.cli import main


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"run_log_dir: {tmp_path / 'runs'}\n")
    return cfg


def _run(tmp_path: Path, monkeypatch, *quest_args: str):
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--type",
            "area",
            "--title",
            "Health",
            *quest_args,
            "--apply",
        ]
    )
    return rc, vault


def test_quest_kind_flag_emits_new_key(tmp_path: Path, capsys, monkeypatch):
    rc, _ = _run(tmp_path, monkeypatch, "--quest-kind", "main")
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["frontmatter"]["quest-kind"] == "main"
    assert "quest" not in payload["plan"]["frontmatter"]


def test_deprecated_quest_alias_still_works_and_warns(tmp_path: Path, capsys, monkeypatch):
    with pytest.warns(LegacyQuestKeyWarning):
        rc, _ = _run(tmp_path, monkeypatch, "--quest", "main")
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    # The alias feeds the same canonical key.
    assert payload["plan"]["frontmatter"]["quest-kind"] == "main"


def test_quest_kind_wins_over_deprecated_alias(tmp_path: Path, capsys, monkeypatch):
    with pytest.warns(LegacyQuestKeyWarning):
        rc, _ = _run(tmp_path, monkeypatch, "--quest", "side", "--quest-kind", "main")
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["frontmatter"]["quest-kind"] == "main"


def test_default_quest_kind_is_none(tmp_path: Path, capsys, monkeypatch):
    rc, _ = _run(tmp_path, monkeypatch)
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["frontmatter"]["quest-kind"] == "none"

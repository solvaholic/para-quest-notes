"""Smoke tests for ``pqn-create`` CLI."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_cli_dry_run_text(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--type",
            "project",
            "--title",
            "Brew Setup",
            "--supports",
            "[[Coffee]]",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY-RUN" in out
    assert "would write projects/Brew Setup.md" in out


def test_cli_apply_json(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--type",
            "project",
            "--title",
            "Brew Setup",
            "--supports",
            "[[Coffee]]",
            "--apply",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["written"] is True
    assert payload["plan"]["destination"] == "projects/Brew Setup.md"


def test_cli_escalation_returns_1(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--type",
            "project",
            "--title",
            "x/y",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["escalation"]["step"] == "validate_inputs"

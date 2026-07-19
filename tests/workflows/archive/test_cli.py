"""Smoke tests for ``pqn-archive`` CLI."""

from __future__ import annotations

import json
from pathlib import Path

from para_quest_notes.workflows.archive.cli import main


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
    (vault / "projects" / "X.md").write_text(
        "---\ntype: project\nquest-kind: none\nsupports: ['[[Q]]']\n---\n## Outcome\ndone\n"
    )
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "X",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY-RUN" in out
    assert "would move projects/X.md -> archive/projects/X.md" in out


def test_cli_apply_json(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "X.md").write_text(
        "---\ntype: project\nquest-kind: none\nsupports: ['[[Q]]']\n---\n## Outcome\ndone\n"
    )
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
            "X",
            "--apply",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["moved"] is True
    assert payload["plan"]["destination"] == "archive/projects/X.md"


def test_cli_escalation_returns_1(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "X.md").write_text(
        "---\ntype: project\nquest-kind: none\nsupports: ['[[Q]]']\n---\n# X\n"
    )
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
            "X",  # missing --outcome
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["escalation"]["step"] == "prepare_outcome"
    assert payload["plan"]["outcome_action"] == "required"


def test_cli_rejects_generate_outcome_with_outcome(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "projects" / "X.md").write_text(
        "---\ntype: project\nquest-kind: none\nsupports: ['[[Q]]']\n---\n# X\n"
    )
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "X",
            "--generate-outcome",
            "--outcome",
            "done",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "mutually exclusive" in captured.err

"""Smoke tests for ``pqn-daily`` CLI."""

from __future__ import annotations

import json
from pathlib import Path

from para_quest_notes.workflows.daily.cli import main


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
    (vault / "inbox" / "2026-05-12.md").write_text("body\n")
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(["--vault", str(vault), "--config", str(cfg), "2026-05-12"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DRY-RUN" in out
    assert "would move inbox/2026-05-12.md -> resources/daily_notes/2026/05/2026-05-12.md" in out


def test_cli_apply_json(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox" / "2026-05-12.md").write_text("body\n")
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
            "2026-05-12",
            "--apply",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["moved"] is True
    assert payload["plan"]["destination"] == "resources/daily_notes/2026/05/2026-05-12.md"
    assert payload["plan"]["h1_inserted"] is True


def test_cli_escalation_returns_one(tmp_path: Path, capsys, monkeypatch):
    vault = _seed_vault(tmp_path)
    (vault / "inbox" / "not-a-date.md").write_text("body\n")
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
            "inbox/not-a-date.md",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["ok"] is False
    assert payload["escalation"]["step"] == "detect_shape"


def test_cli_vault_missing(tmp_path: Path, capsys, monkeypatch):
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(tmp_path / "no-such-vault"),
            "--config",
            str(cfg),
            "2026-05-12",
        ]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "error:" in err

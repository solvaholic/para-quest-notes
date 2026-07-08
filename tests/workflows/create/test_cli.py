"""Smoke tests for ``pqn-create`` CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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


# ---- Path inference (#45) -----------------------------------------------


def test_cli_positional_path_infers_type_and_title(tmp_path: Path, capsys, monkeypatch):
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
            "--supports",
            "[[Health]]",
            "projects/Brew Setup.md",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["destination"] == "projects/Brew Setup.md"


def test_cli_positional_path_infers_sub_path(tmp_path: Path, capsys, monkeypatch):
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
            "--supports",
            "[[Health]]",
            "projects/2026/Brew Setup.md",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["destination"] == "projects/2026/Brew Setup.md"


def test_cli_explicit_flags_override_inferred(tmp_path: Path, capsys, monkeypatch):
    """Explicit --type and --title override values inferred from path."""
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
            "area",
            "--title",
            "Real Title",
            "--supports",
            "[[Health]]",
            "projects/Ignored Title.md",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    # Explicit --type area and --title "Real Title" override path inference
    assert payload["plan"]["destination"] == "areas/Real Title.md"


def test_cli_positional_path_infers_vault(tmp_path: Path, capsys, monkeypatch):
    """Path with vault prefix infers --vault."""
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    # Use the full vault path as a prefix in the positional arg
    rc = main(
        [
            "--config",
            str(cfg),
            "--format",
            "json",
            "--supports",
            "[[Health]]",
            f"{vault}/projects/Brew Setup.md",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["destination"] == "projects/Brew Setup.md"


def test_cli_invalid_path_returns_2(tmp_path: Path, capsys, monkeypatch):
    """Invalid positional path (no PARA dir) returns exit code 2."""
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "random/stuff/Note.md",
        ]
    )
    err = capsys.readouterr().err
    assert rc == 2
    assert "PARA directory" in err


def test_cli_no_type_no_path_returns_2(tmp_path: Path, capsys, monkeypatch):
    """Neither --type nor positional path results in exit code 2."""
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--vault",
                str(vault),
                "--config",
                str(cfg),
                "--title",
                "Foo",
            ]
        )
    assert exc.value.code == 2

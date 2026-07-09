"""Tests for pqn-create Quest resolution via resolve_quest step (#48)."""

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


def test_resolve_quest_from_sub_path(tmp_path: Path, capsys, monkeypatch):
    """pqn-create resolves Quest when sub-path matches an area note."""
    vault = _seed_vault(tmp_path)
    # Create an area note that declares a quest
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\nsupports:\n- '[[Health]]'\n---\n# Health\n"
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
            "--type",
            "project",
            "health/Improve PQN",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    # Should resolve to canonical path, not inbox
    assert payload["plan"]["destination"] == "projects/health/Improve PQN.md"
    assert payload["plan"]["destination_mode"] == "canonical"
    # Frontmatter should include supports
    assert "[[Health]]" in payload["plan"]["frontmatter"].get("supports", [])


def test_resolve_quest_deterministic_miss_falls_to_inbox(tmp_path: Path, capsys, monkeypatch):
    """When no area note matches, fall back to inbox."""
    vault = _seed_vault(tmp_path)
    # Area note exists but doesn't match the sub-path
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\nsupports:\n- '[[Health]]'\n---\n# Health\n"
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
            "--type",
            "project",
            "--title",
            "Unrelated Thing",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    # Should fall back to inbox
    assert payload["plan"]["destination"] == "inbox/Unrelated Thing.md"
    assert payload["plan"]["destination_mode"] == "inbox"


def test_resolve_quest_full_path_inference(tmp_path: Path, capsys, monkeypatch):
    """Full path like 'projects/health/Improve PQN' resolves Quest."""
    vault = _seed_vault(tmp_path)
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\nsupports:\n- '[[Health]]'\n---\n# Health\n"
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
            "projects/health/Improve PQN",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["destination"] == "projects/health/Improve PQN.md"
    assert payload["plan"]["destination_mode"] == "canonical"


def test_resolve_quest_no_vault_quests(tmp_path: Path, capsys, monkeypatch):
    """When vault has no quests, fall back to inbox."""
    vault = _seed_vault(tmp_path)
    # No area notes with quest declarations
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
            "health/My Project",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["destination"] == "inbox/My Project.md"
    assert payload["plan"]["destination_mode"] == "inbox"


def test_resolve_quest_skipped_when_supports_provided(tmp_path: Path, capsys, monkeypatch):
    """When --supports is explicit, resolve_quest is skipped."""
    vault = _seed_vault(tmp_path)
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\nsupports:\n- '[[Health]]'\n---\n# Health\n"
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
            "--type",
            "project",
            "--supports",
            "[[Create]]",
            "health/Improve PQN",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    # Explicit --supports wins, not resolved from area note
    assert payload["plan"]["frontmatter"]["supports"] == ["[[Create]]"]
    assert payload["plan"]["destination"] == "projects/health/Improve PQN.md"


def test_resolve_quest_plan_notes_updated(tmp_path: Path, capsys, monkeypatch):
    """On resolution, plan notes reflect the quest source."""
    vault = _seed_vault(tmp_path)
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest: main\nsupports:\n- '[[Health]]'\n---\n# Health\n"
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
            "--type",
            "project",
            "health/Improve PQN",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    notes = payload["plan"]["notes"]
    # Should have a resolution note, NOT the inbox fallback note
    assert any("quest resolved" in n for n in notes)
    assert not any("filed to inbox" in n for n in notes)

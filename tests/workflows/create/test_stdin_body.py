"""Tests for pqn-create stdin body intake (#46)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from para_quest_notes.adapter.llm import OllamaClient
from para_quest_notes.workflows.create.cli import main
from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note
from para_quest_notes.workflows.validate.api import validate_paths


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def _config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"run_log_dir: {tmp_path / 'runs'}\n")
    return cfg


def test_stdin_body_replaces_skeleton(tmp_path: Path, capsys, monkeypatch):
    """Stdin body content replaces the default skeleton."""
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    body = "# My Project\n\nThis is my custom body content.\n"
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--type",
            "project",
            "--title",
            "My Project",
            "--supports",
            "[[Health]]",
            "--body-stdin",
            "--apply",
        ],
        stdin=body,
    )
    assert rc == 0
    written = (vault / "projects/My Project.md").read_text()
    # Should contain the stdin body, not the skeleton
    assert "This is my custom body content." in written
    assert "<one-sentence purpose>" not in written
    # Frontmatter still comes first
    assert written.startswith("---\n")


def test_stdin_body_json_output(tmp_path: Path, capsys, monkeypatch):
    """JSON output works with stdin body."""
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    body = "# Notes\n\nBody from pipe.\n"
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--type",
            "resource",
            "--title",
            "Piped Resource",
            "--body-stdin",
        ],
        stdin=body,
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True
    assert payload["plan"]["destination"] == "resources/Piped Resource.md"
    assert payload["plan"]["body_source"] == "stdin"


def test_empty_stdin_uses_skeleton(tmp_path: Path, capsys, monkeypatch):
    """Empty stdin (whitespace-only) falls back to the skeleton."""
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
            "Empty Body",
            "--supports",
            "[[Health]]",
            "--body-stdin",
            "--apply",
        ],
        stdin="   \n\n  ",
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["body_source"] == "skeleton"
    written = (vault / "projects/Empty Body.md").read_text()
    # Should use the skeleton since stdin was empty
    assert "<one-sentence purpose>" in written


def test_no_body_stdin_flag_uses_skeleton(tmp_path: Path, capsys, monkeypatch):
    """Without --body-stdin, the skeleton is used even if stdin arg provided."""
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
            "No Stdin",
            "--supports",
            "[[Health]]",
            "--apply",
        ],
        # stdin kwarg NOT passed, no --body-stdin flag
    )
    assert rc == 0
    written = (vault / "projects/No Stdin.md").read_text()
    assert "<one-sentence purpose>" in written


def test_stdin_body_preserves_frontmatter(tmp_path: Path, capsys, monkeypatch):
    """Stdin body doesn't interfere with canonical frontmatter generation."""
    vault = _seed_vault(tmp_path)
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)
    body = "Custom body with no frontmatter of its own.\n"
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
            "Custom Area",
            "--quest-kind",
            "main",
            "--body-stdin",
            "--apply",
        ],
        stdin=body,
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    # Frontmatter is still generated by the workflow
    assert payload["plan"]["frontmatter"]["type"] == "area"
    assert payload["plan"]["frontmatter"]["quest-kind"] == "main"
    # Read the file to verify
    written = (vault / "areas/Custom Area.md").read_text()
    assert "Custom body with no frontmatter" in written
    assert "type: area" in written


def test_stdin_body_renders_every_template_variable_on_copied_sample_vault(tmp_path: Path):
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)
    body = (
        "# $title\n\n"
        "type=$type\n"
        "quest-kind=$quest_kind\n"
        "deprecated-alias=$quest\n"
        "supports=$supports\n"
        "source=$source_url\n"
        "created=$created\n"
        "literal=$$title and $$5\n"
        "unknown=$UNKNOWN and ${other}\n"
    )

    result = create_note(
        CreateInputs(
            title="Rendered Stdin",
            type="resource",
            quest="none",
            supports=["[[Health]]", "[[Maintain Home]]"],
            source_url="https://example.com/source",
            body=body,
        ),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    expected = (
        "---\n"
        "type: resource\n"
        "quest-kind: none\n"
        "supports:\n"
        "- '[[Health]]'\n"
        "- '[[Maintain Home]]'\n"
        "source_url: https://example.com/source\n"
        "created: '2026-09-04'\n"
        "---\n"
        "# Rendered Stdin\n\n"
        "type=resource\n"
        "quest-kind=none\n"
        "deprecated-alias=none\n"
        "supports=[[Health]], [[Maintain Home]]\n"
        "source=https://example.com/source\n"
        "created=2026-09-04\n"
        "literal=$title and $5\n"
        "unknown=$UNKNOWN and ${other}\n"
    )
    destination = vault / "resources/Rendered Stdin.md"
    assert result.ok is True
    assert result.written is True
    assert result.plan.body_source == "stdin"
    assert destination.read_text() == expected
    assert validate_paths(vault, [destination]).issues == []


def test_stdin_body_uses_positional_and_resolved_quest_values(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    vault = _seed_vault(tmp_path)
    (vault / "areas/Health.md").write_text(
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n# Health\n"
    )
    cfg = _config(tmp_path)
    monkeypatch.delenv("PARA_QUEST_VAULT", raising=False)

    def fail_on_llm_call(*args, **kwargs):
        raise AssertionError("pqn-create stdin rendering must not call an LLM")

    monkeypatch.setattr(OllamaClient, "generate", fail_on_llm_call)
    rc = main(
        [
            "--vault",
            str(vault),
            "--config",
            str(cfg),
            "--format",
            "json",
            "--body-stdin",
            "--apply",
            "projects/health/Resolved Stdin.md",
        ],
        stdin="# $title\n\n$type supports $supports.\n",
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["destination"] == "projects/health/Resolved Stdin.md"
    assert payload["plan"]["frontmatter"]["supports"] == ["[[Health]]"]
    assert payload["plan"]["body_source"] == "stdin"
    written = (vault / "projects/health/Resolved Stdin.md").read_text()
    assert written.endswith("# Resolved Stdin\n\nproject supports [[Health]].\n")


def test_stdin_body_renders_missing_optional_values_after_inbox_fallback(
    tmp_path: Path,
):
    vault = _seed_vault(tmp_path)

    result = create_note(
        CreateInputs(
            title="Inbox Stdin",
            type="project",
            body="supports=<$supports> source=<$source_url> kind=$quest_kind\n",
        ),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    assert result.plan.destination == "inbox/Inbox Stdin.md"
    assert result.plan.destination_mode == "inbox"
    assert result.plan.body_source == "stdin"
    assert (
        (vault / "inbox/Inbox Stdin.md").read_text().endswith("supports=<> source=<> kind=none\n")
    )


def test_stdin_body_overrides_config_template_without_parsing_stdin_frontmatter(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/default.md").write_text(
        "---\nstatus: from-template\n---\nTEMPLATE BODY\n"
    )
    cfg = _config(
        tmp_path,
    )
    cfg.write_text(
        f"run_log_dir: {tmp_path / 'runs'}\n"
        "workflows:\n"
        "  create:\n"
        "    defaults:\n"
        "      resource: default\n"
    )
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
            "resource",
            "--title",
            "Stdin Metadata",
            "--body-stdin",
            "--apply",
        ],
        stdin="---\nstdin_key: literal\n---\n# $title\n",
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["body_source"] == "stdin"
    assert "status" not in payload["plan"]["frontmatter"]
    assert "stdin_key" not in payload["plan"]["frontmatter"]
    written = (vault / "resources/Stdin Metadata.md").read_text()
    assert written.endswith("---\nstdin_key: literal\n---\n# Stdin Metadata\n")
    assert "TEMPLATE BODY" not in written

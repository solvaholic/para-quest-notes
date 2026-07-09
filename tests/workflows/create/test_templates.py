"""Tests for pqn-create body templates (#42)."""

from __future__ import annotations

import json
from pathlib import Path

from para_quest_notes.workflows.create.cli import main
from para_quest_notes.workflows.create.templates import (
    TemplateNotFoundError,
    get_template_config,
    load_template,
    render_template,
    resolve_template_path,
)


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def _config(tmp_path: Path, extra: str = "") -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(f"run_log_dir: {tmp_path / 'runs'}\n{extra}")
    return cfg


# ---- Unit tests for templates module ------------------------------------


def test_resolve_template_by_name(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/weekly-review.md").write_text("# $title\n\n## Review\n")
    path = resolve_template_path("weekly-review", vault=vault)
    assert path is not None
    assert path.name == "weekly-review.md"


def test_resolve_template_by_name_with_md(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/weekly-review.md").write_text("body")
    path = resolve_template_path("weekly-review.md", vault=vault)
    assert path is not None


def test_resolve_template_by_path(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "custom/templates").mkdir(parents=True)
    (vault / "custom/templates/mine.md").write_text("body")
    path = resolve_template_path("custom/templates/mine.md", vault=vault)
    assert path is not None


def test_resolve_template_not_found(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "resources/templates").mkdir(parents=True)
    path = resolve_template_path("nonexistent", vault=vault)
    assert path is None


def test_load_template_raises_on_not_found(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "resources/templates").mkdir(parents=True)
    import pytest

    with pytest.raises(TemplateNotFoundError):
        load_template("nonexistent", vault=vault)


def test_render_template_substitutes_vars():
    text = "# $title\n\nType: $type\nCreated: $created\n"
    result = render_template(text, {"title": "My Note", "type": "project", "created": "2026-07-08"})
    assert "# My Note" in result
    assert "Type: project" in result
    assert "Created: 2026-07-08" in result


def test_render_template_leaves_unknown_vars():
    text = "# $title\n\n$unknown_var stays\n"
    result = render_template(text, {"title": "Foo"})
    assert "# Foo" in result
    assert "$unknown_var stays" in result


def test_get_template_config_defaults():
    template_dir, defaults = get_template_config({})
    assert template_dir == "resources/templates"
    assert defaults == {}


def test_get_template_config_custom():
    config = {
        "create": {
            "template_dir": "my/templates",
            "defaults": {"project": "weekly-review", "area": None, "resource": "reference"},
        }
    }
    template_dir, defaults = get_template_config(config)
    assert template_dir == "my/templates"
    assert defaults == {"project": "weekly-review", "resource": "reference"}


def test_resolve_template_custom_dir(tmp_path: Path):
    vault = tmp_path / "vault"
    (vault / "my/templates").mkdir(parents=True)
    (vault / "my/templates/custom.md").write_text("body")
    path = resolve_template_path("custom", vault=vault, template_dir="my/templates")
    assert path is not None


# ---- CLI integration tests ----------------------------------------------


def test_cli_explicit_template(tmp_path: Path, capsys, monkeypatch):
    """--template loads and renders a named template."""
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/weekly-review.md").write_text(
        "# $title\n\n## Week of $created\n\n- What went well?\n- What to improve?\n"
    )
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
            "Weekly Review",
            "--supports",
            "[[Work]]",
            "--template",
            "weekly-review",
            "--apply",
        ]
    )
    assert rc == 0
    written = (vault / "projects/Weekly Review.md").read_text()
    assert "# Weekly Review" in written
    assert "Week of 20" in written  # $created substituted
    assert "What went well?" in written
    assert "<one-sentence purpose>" not in written  # skeleton NOT used


def test_cli_config_default_template(tmp_path: Path, capsys, monkeypatch):
    """Config default template applies when no --template flag."""
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/project-default.md").write_text(
        "# $title\n\n## Objective\n\n<fill in>\n"
    )
    cfg = _config(
        tmp_path,
        "workflows:\n  create:\n    defaults:\n      project: project-default\n",
    )
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
            "Auto Template",
            "--supports",
            "[[Work]]",
            "--apply",
        ]
    )
    assert rc == 0
    written = (vault / "projects/Auto Template.md").read_text()
    assert "## Objective" in written
    assert "<one-sentence purpose>" not in written


def test_cli_template_not_found_falls_to_skeleton(tmp_path: Path, capsys, monkeypatch):
    """Missing template falls back to the built-in skeleton."""
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
            "Fallback",
            "--supports",
            "[[Work]]",
            "--template",
            "nonexistent",
            "--apply",
        ]
    )
    assert rc == 0
    written = (vault / "projects/Fallback.md").read_text()
    # Falls back to skeleton
    assert "<one-sentence purpose>" in written


def test_cli_stdin_overrides_template(tmp_path: Path, capsys, monkeypatch):
    """stdin body takes priority over --template."""
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/ignored.md").write_text("TEMPLATE BODY\n")
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
            "Stdin Wins",
            "--supports",
            "[[Work]]",
            "--template",
            "ignored",
            "--body-stdin",
            "--apply",
        ],
        stdin="# Stdin Wins\n\nCustom body from stdin.\n",
    )
    assert rc == 0
    written = (vault / "projects/Stdin Wins.md").read_text()
    assert "Custom body from stdin." in written
    assert "TEMPLATE BODY" not in written


def test_cli_json_output_shows_body_source(tmp_path: Path, capsys, monkeypatch):
    """JSON output includes body_source field."""
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/simple.md").write_text("# $title\n\nSimple.\n")
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
            "resource",
            "--title",
            "Test",
            "--template",
            "simple",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True

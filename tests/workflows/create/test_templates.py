"""Tests for pqn-create note templates (#42, #75)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from para_quest_notes.workflows.create.cli import main
from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note
from para_quest_notes.workflows.create.templates import (
    TemplateNotFoundError,
    get_template_config,
    load_template,
    render_template,
    resolve_template_path,
)
from para_quest_notes.workflows.validate.api import validate_paths


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


def test_cli_template_quest_kind_and_deprecated_alias(tmp_path: Path, monkeypatch):
    """Both `$quest_kind` and the deprecated `$quest` expand in templates (#98)."""
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/kind-demo.md").write_text(
        "# $title\n\nkind=$quest_kind alias=$quest\n"
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
            "area",
            "--title",
            "Kinded",
            "--quest-kind",
            "main",
            "--template",
            "kind-demo",
            "--apply",
        ]
    )
    assert rc == 0
    written = (vault / "areas/Kinded.md").read_text()
    # Both variables resolve to the same quest-kind value; neither is left literal.
    assert "kind=main alias=main" in written
    assert "$quest" not in written


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
            "--format",
            "json",
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
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["body_source"] == "template:weekly-review"
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
        "---\nstatus: draft\nreview_cycle: weekly\n---\n# $title\n\n## Objective\n\n<fill in>\n"
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
            "--format",
            "json",
            "--type",
            "project",
            "--title",
            "Auto Template",
            "--supports",
            "[[Work]]",
            "--apply",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["body_source"] == "template:project-default"
    written = (vault / "projects/Auto Template.md").read_text()
    assert "status: draft" in written
    assert "review_cycle: weekly" in written
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
            "--format",
            "json",
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
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["body_source"] == "skeleton (template not found)"
    written = (vault / "projects/Fallback.md").read_text()
    # Falls back to skeleton
    assert "<one-sentence purpose>" in written


def test_cli_stdin_overrides_template(tmp_path: Path, capsys, monkeypatch):
    """stdin body takes priority over --template."""
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/ignored.md").write_text(
        "---\nstatus: from-template\n---\nTEMPLATE BODY\n"
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
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["body_source"] == "stdin"
    written = (vault / "projects/Stdin Wins.md").read_text()
    assert "Custom body from stdin." in written
    assert "TEMPLATE BODY" not in written
    assert "status:" not in written


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
    assert payload["plan"]["body_source"] == "template:simple"


def test_cli_json_output_reports_skeleton_body_source(tmp_path: Path, capsys, monkeypatch):
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
            "resource",
            "--title",
            "Skeleton Source",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["plan"]["body_source"] == "skeleton"


# ---- Whole-note template integration (#75) -------------------------------


def test_whole_note_template_merges_supplemental_metadata_under_generated_values(
    tmp_path: Path,
):
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/whole-note.md").write_text(
        "---\n"
        "type: area\n"
        "quest-kind: side\n"
        "supports:\n"
        "- '[[Template Quest]]'\n"
        "source_url: https://template.example/source\n"
        "created: '2000-01-01'\n"
        "status: draft\n"
        "review_cycle: weekly\n"
        "tags:\n"
        "- review\n"
        "priority: 2\n"
        "published: false\n"
        "empty_value:\n"
        "---\n"
        "# $title\n\n"
        "Kind: $quest_kind\n"
        "Supports: $supports\n"
        "Source: $source_url\n"
        "Created: $created\n"
    )

    result = create_note(
        CreateInputs(
            title="Weekly Review",
            type="project",
            quest="none",
            supports=["[[Work]]"],
            source_url="https://cli.example/source",
            template="whole-note",
        ),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    expected_frontmatter = {
        "type": "project",
        "quest-kind": "none",
        "supports": ["[[Work]]"],
        "source_url": "https://cli.example/source",
        "created": "2026-09-04",
        "status": "draft",
        "review_cycle": "weekly",
        "tags": ["review"],
        "priority": 2,
        "published": False,
    }
    assert result.ok is True
    assert result.written is True
    assert result.plan.frontmatter == expected_frontmatter
    assert (vault / "projects/Weekly Review.md").read_text() == (
        "---\n"
        "type: project\n"
        "quest-kind: none\n"
        "supports:\n"
        "- '[[Work]]'\n"
        "source_url: https://cli.example/source\n"
        "created: '2026-09-04'\n"
        "status: draft\n"
        "review_cycle: weekly\n"
        "tags:\n"
        "- review\n"
        "priority: 2\n"
        "published: false\n"
        "---\n"
        "# Weekly Review\n\n"
        "Kind: none\n"
        "Supports: [[Work]]\n"
        "Source: https://cli.example/source\n"
        "Created: 2026-09-04\n"
    )


def test_body_only_template_output_is_unchanged(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/body-only.md").write_text(
        "# $title\n\nDollar: $$title\nUnknown: $PATH\n"
    )

    result = create_note(
        CreateInputs(
            title="Body Only",
            type="project",
            supports=["[[Work]]"],
            template="body-only",
        ),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    assert result.ok is True
    assert (vault / "projects/Body Only.md").read_text() == (
        "---\n"
        "type: project\n"
        "quest-kind: none\n"
        "supports:\n"
        "- '[[Work]]'\n"
        "created: '2026-09-04'\n"
        "---\n"
        "# Body Only\n\n"
        "Dollar: $title\n"
        "Unknown: $PATH\n"
    )


def test_legacy_backmatter_is_migrated_beneath_frontmatter_and_generated_values(
    tmp_path: Path,
):
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/legacy.md").write_text(
        "---\n"
        "status: front\n"
        "quest: side\n"
        "---\n"
        "# $title\n\n"
        "Body.\n\n"
        "---\n"
        "status: back\n"
        "review_cycle: monthly\n"
        "type: area\n"
        "---\n"
    )

    result = create_note(
        CreateInputs(
            title="Legacy Template",
            type="project",
            supports=["[[Work]]"],
            template="legacy",
        ),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    assert result.plan.frontmatter == {
        "type": "project",
        "quest-kind": "none",
        "supports": ["[[Work]]"],
        "created": "2026-09-04",
        "status": "front",
        "review_cycle": "monthly",
    }
    written = (vault / "projects/Legacy Template.md").read_text()
    assert written.endswith("# Legacy Template\n\nBody.\n\n")
    assert written.count("---\n") == 2
    assert "quest:" not in written


@pytest.mark.parametrize(
    "template_text",
    [
        "---\nstatus: [\n---\n# $title\n",
        "---\n- status\n- draft\n---\n# $title\n",
        "# $title\n\n---\nstatus: [\n---\n",
    ],
)
def test_malformed_or_non_mapping_metadata_is_preserved_as_body(
    tmp_path: Path,
    template_text: str,
):
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/malformed.md").write_text(template_text)

    result = create_note(
        CreateInputs(
            title="Malformed Template",
            type="resource",
            template="malformed",
        ),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    assert result.ok is True
    assert result.plan.frontmatter == {
        "type": "resource",
        "quest-kind": "none",
        "created": "2026-09-04",
    }
    rendered_body = render_template(template_text, {"title": "Malformed Template"})
    assert (vault / "resources/Malformed Template.md").read_text().endswith(rendered_body)


def test_cli_dry_run_json_reports_merged_frontmatter_without_writing(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/dry-run.md").write_text(
        "---\nstatus: draft\ntags: [review, weekly]\n---\n# $title\n"
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
            "Dry Run",
            "--supports",
            "[[Work]]",
            "--template",
            "dry-run",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["written"] is False
    assert payload["plan"]["frontmatter"]["status"] == "draft"
    assert payload["plan"]["frontmatter"]["tags"] == ["review", "weekly"]
    assert not (vault / "projects/Dry Run.md").exists()


def test_inbox_fallback_keeps_supplemental_metadata_but_generated_omissions_win(
    tmp_path: Path,
):
    vault = _seed_vault(tmp_path)
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/inbox.md").write_text(
        "---\n"
        "supports: ['[[Template Quest]]']\n"
        "source_url: https://template.example/source\n"
        "status: needs-triage\n"
        "---\n"
        "# $title\n"
    )

    result = create_note(
        CreateInputs(title="Inbox Template", type="project", template="inbox"),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    assert result.plan.destination == "inbox/Inbox Template.md"
    assert result.plan.destination_mode == "inbox"
    assert result.plan.frontmatter == {
        "type": "project",
        "quest-kind": "none",
        "created": "2026-09-04",
        "status": "needs-triage",
    }
    written = (vault / "inbox/Inbox Template.md").read_text()
    assert "supports:" not in written
    assert "source_url:" not in written
    assert "status: needs-triage" in written


def test_whole_note_template_does_not_overwrite_existing_note(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    destination = vault / "projects" / "Existing Note.md"
    destination.write_text("# Existing Note\n\nKeep me.\n")
    (vault / "resources/templates").mkdir(parents=True)
    (vault / "resources/templates/whole-note.md").write_text(
        "---\nstatus: replacement\n---\n# $title\n"
    )

    result = create_note(
        CreateInputs(
            title="Existing Note",
            type="project",
            supports=["[[Work]]"],
            template="whole-note",
        ),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    assert result.ok is False
    assert result.written is False
    assert result.escalation is not None
    assert result.escalation["step"] == "check_collision"
    assert destination.read_text() == "# Existing Note\n\nKeep me.\n"


def test_whole_note_template_apply_smokes_copied_sample_vault(tmp_path: Path):
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    vault = tmp_path / "vault"
    shutil.copytree(sample, vault)
    template_dir = vault / "resources" / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "whole-note-smoke.md").write_text(
        "---\nstatus: draft\nreviewers: [owner]\n---\n# $title\n\nCreated $created.\n"
    )

    result = create_note(
        CreateInputs(
            title="Whole Note Template Smoke",
            type="project",
            supports=["[[Health]]"],
            template="whole-note-smoke",
        ),
        vault=vault,
        apply=True,
        today="2026-09-04",
    )

    payload = result.to_dict()
    destination = vault / "projects" / "Whole Note Template Smoke.md"
    assert payload["ok"] is True
    assert payload["written"] is True
    assert payload["plan"]["destination"] == "projects/Whole Note Template Smoke.md"
    assert payload["plan"]["frontmatter"]["status"] == "draft"
    assert payload["plan"]["frontmatter"]["reviewers"] == ["owner"]
    assert destination.read_text().endswith("# Whole Note Template Smoke\n\nCreated 2026-09-04.\n")
    assert validate_paths(vault, [destination]).issues == []

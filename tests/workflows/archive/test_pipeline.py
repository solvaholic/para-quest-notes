"""End-to-end ``pqn-archive`` pipeline tests (no LLM)."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.workflows.archive.contract import ArchiveInputs
from para_quest_notes.workflows.archive.pipeline import archive_note


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def test_dry_run_plans_without_writing(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Brew Setup.md"
    src.write_text(
        "---\ntype: project\nquest: none\nsupports:\n- '[[Coffee]]'\n---\n"
        "# Brew Setup\n\n## Outcome\nShipped it.\n"
    )
    inputs = ArchiveInputs(target="Brew Setup")

    result = archive_note(inputs, vault=vault, apply=False, today="2026-05-12")

    assert result.ok
    assert not result.moved
    assert result.plan.source == "projects/Brew Setup.md"
    assert result.plan.destination == "archive/projects/Brew Setup.md"
    assert result.plan.outcome_action == "kept"
    assert src.exists()
    assert not (vault / "archive" / "projects" / "Brew Setup.md").exists()


def test_apply_moves_and_cancels_tasks(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Brew Setup.md"
    src.write_text(
        "---\ntype: project\nquest: none\nsupports:\n- '[[Coffee]]'\n---\n"
        "# Brew Setup\n\n- [ ] grind\n- [/] pour\n- [x] taste\n"
    )
    inputs = ArchiveInputs(
        target="Brew Setup",
        outcome="Shipped it.",
        cancel_open_tasks=True,
    )

    result = archive_note(inputs, vault=vault, apply=True, today="2026-05-12")

    assert result.ok, result.escalation or result.error
    assert result.moved
    assert result.plan.tasks_cancelled == 2
    assert result.plan.outcome_action == "provided"

    dest = vault / "archive" / "projects" / "Brew Setup.md"
    assert dest.exists()
    assert not src.exists()
    text = dest.read_text()
    assert "- [-] grind ❌ 2026-05-12" in text
    assert "- [-] pour ❌ 2026-05-12" in text
    assert "## Outcome\n\nShipped it." in text


def test_open_tasks_without_flag_escalates(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text(
        "---\ntype: project\nquest: none\nsupports:\n- '[[Q]]'\n---\n"
        "## Outcome\ndone\n\n- [ ] still open\n"
    )
    inputs = ArchiveInputs(target="X")
    result = archive_note(inputs, vault=vault, apply=True, today="2026-05-12")
    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "decide_task_action"
    assert src.exists()


def test_missing_outcome_escalates(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "X.md"
    src.write_text("---\ntype: project\nquest: none\nsupports:\n- '[[Q]]'\n---\n# X\n")
    inputs = ArchiveInputs(target="X")
    result = archive_note(inputs, vault=vault, apply=True, today="2026-05-12")
    assert not result.ok
    assert result.escalation["step"] == "prepare_outcome"
    assert result.plan.outcome_action == "required"
    assert src.exists()


def test_area_target_escalates(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "areas" / "Home.md").write_text("---\ntype: area\n---\n")
    inputs = ArchiveInputs(target="areas/Home.md", outcome="x")
    result = archive_note(inputs, vault=vault, apply=True, today="2026-05-12")
    assert not result.ok
    assert result.escalation["step"] == "resolve_target"


def test_legacy_backmatter_migrated(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Old.md"
    src.write_text(
        "# Old\n\nbody\n\n## Outcome\ndone\n\n"
        "---\ntype: project\nquest: none\nsupports: ['[[Coffee]]']\n---\n"
    )
    inputs = ArchiveInputs(target="Old")
    result = archive_note(inputs, vault=vault, apply=True, today="2026-05-12")
    assert result.ok, result.escalation or result.error
    assert result.plan.frontmatter_migrated
    dest = vault / "archive" / "projects" / "Old.md"
    text = dest.read_text()
    assert text.startswith("---\ntype: project")
    # No tail backmatter remains.
    assert text.count("---\n") == 2


def test_destination_exists_escalates(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    src = vault / "projects" / "Dup.md"
    src.write_text("---\ntype: project\nquest: none\nsupports: ['[[Q]]']\n---\n## Outcome\ndone\n")
    existing = vault / "archive" / "projects" / "Dup.md"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_text("preexisting")
    inputs = ArchiveInputs(target="Dup")
    result = archive_note(inputs, vault=vault, apply=True, today="2026-05-12")
    assert not result.ok
    assert result.escalation["step"] == "write_and_move"
    assert src.exists()
    assert existing.read_text() == "preexisting"

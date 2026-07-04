"""End-to-end ``pqn-create`` pipeline tests (no LLM)."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def test_dry_run_plans_without_writing(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    inputs = CreateInputs(title="Brew Setup", type="project", supports=["[[Coffee]]"])

    result = create_note(inputs, vault=vault, apply=False, today="2026-01-02")

    assert result.ok
    assert not result.written
    assert result.plan.destination == "projects/Brew Setup.md"
    assert result.plan.frontmatter["type"] == "project"
    assert result.plan.frontmatter["supports"] == ["[[Coffee]]"]
    assert not (vault / "projects" / "Brew Setup.md").exists()


def test_apply_writes_canonical_note(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    inputs = CreateInputs(title="Brew Setup", type="project", supports=["[[Coffee]]"])

    result = create_note(inputs, vault=vault, apply=True, today="2026-01-02")

    assert result.ok
    assert result.written
    dest = vault / "projects" / "Brew Setup.md"
    assert dest.exists()
    text = dest.read_text()
    # Canonical key order: type, quest, supports, created (source_url omitted)
    assert text.startswith("---\ntype: project\nquest: none\nsupports:\n- '[[Coffee]]'")
    assert "# Brew Setup" in text


def test_collision_escalates_and_does_not_write(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    (vault / "areas" / "Twin.md").write_text(
        "---\ntype: area\nquest: main\nsupports: ['[[X]]']\n---\n"
    )
    inputs = CreateInputs(title="Twin", type="project", supports=["[[Coffee]]"])

    result = create_note(inputs, vault=vault, apply=True, today="2026-01-02")

    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "check_collision"
    assert not (vault / "projects" / "Twin.md").exists()


def test_resource_with_subpath_and_url(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    inputs = CreateInputs(
        title="Pour Over Guide",
        type="resource",
        quest="none",
        sub_path="coffee",
        source_url="https://example.com/guide",
    )

    result = create_note(inputs, vault=vault, apply=True, today="2026-01-02")

    assert result.ok
    dest = vault / "resources" / "coffee" / "Pour Over Guide.md"
    assert dest.exists()
    text = dest.read_text()
    assert "type: resource" in text
    assert "supports:" not in text
    assert "source_url: https://example.com/guide" in text
    assert "https://example.com/guide" in text  # also in body


def test_validate_inputs_escalation_short_circuits(tmp_path: Path):
    vault = _seed_vault(tmp_path)
    inputs = CreateInputs(title="x/y", type="project")
    result = create_note(inputs, vault=vault, apply=True)
    assert not result.ok
    assert result.escalation is not None
    assert result.escalation["step"] == "validate_inputs"


def test_quest_main_without_supports_files_to_canonical(tmp_path: Path):
    """#41: --quest main without --supports infers supports and files to areas/."""
    vault = _seed_vault(tmp_path)
    inputs = CreateInputs(title="Coffee", type="area", quest="main")

    result = create_note(inputs, vault=vault, apply=True, today="2026-07-04")

    assert result.ok
    assert result.written
    assert result.plan.destination == "areas/Coffee.md"
    assert result.plan.destination_mode == "canonical"
    assert result.plan.frontmatter["supports"] == ["[[Coffee]]"]
    dest = vault / "areas" / "Coffee.md"
    assert dest.exists()
    text = dest.read_text()
    assert "type: area" in text
    assert "quest: main" in text
    assert "[[Coffee]]" in text

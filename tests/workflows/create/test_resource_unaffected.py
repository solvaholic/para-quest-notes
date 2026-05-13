"""Resource behavior should stay canonical when supports is omitted."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def test_resource_unaffected(tmp_path: Path):
    vault = _seed_vault(tmp_path)

    result = create_note(
        CreateInputs(title="Reference", type="resource", source_url="https://example.com"),
        vault=vault,
        apply=False,
        today="2026-01-02",
    )

    assert result.ok
    assert result.plan.destination == "resources/Reference.md"
    assert result.plan.destination_mode == "canonical"
    assert result.plan.notes == []
    assert result.plan.frontmatter["type"] == "resource"
    assert "supports" not in result.plan.frontmatter

"""Regression coverage for canonical ``pqn-create`` paths."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def test_canonical_path_preserved(tmp_path: Path):
    vault = _seed_vault(tmp_path)

    result = create_note(
        CreateInputs(title="Test Thing", type="project", supports=["[[Connect]]"]),
        vault=vault,
        apply=False,
        today="2026-01-02",
    )

    assert result.ok
    assert result.plan.destination == "projects/Test Thing.md"
    assert result.plan.destination_mode == "canonical"
    assert result.plan.notes == []
    assert result.plan.frontmatter["supports"] == ["[[Connect]]"]

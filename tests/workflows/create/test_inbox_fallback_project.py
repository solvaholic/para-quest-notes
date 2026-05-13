"""Inbox fallback planning tests for ``pqn-create``."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def test_inbox_fallback_project(tmp_path: Path):
    vault = _seed_vault(tmp_path)

    result = create_note(
        CreateInputs(title="Test Thing", type="project"),
        vault=vault,
        apply=False,
        today="2026-01-02",
    )

    assert result.ok
    assert result.plan.destination == "inbox/Test Thing.md"
    assert result.plan.destination_mode == "inbox"
    assert result.plan.notes == [
        "filed to inbox because no --supports was provided for type=project"
    ]


def test_inbox_fallback_area(tmp_path: Path):
    vault = _seed_vault(tmp_path)

    result = create_note(
        CreateInputs(title="Test Thing", type="area"),
        vault=vault,
        apply=False,
        today="2026-01-02",
    )

    assert result.ok
    assert result.plan.destination == "inbox/Test Thing.md"
    assert result.plan.destination_mode == "inbox"
    assert result.plan.notes == ["filed to inbox because no --supports was provided for type=area"]

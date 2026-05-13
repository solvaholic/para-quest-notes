"""Apply-mode coverage for ``pqn-create`` inbox fallback."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import create_note


def _seed_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    for d in ("inbox", "areas", "projects", "resources", "archive"):
        (vault / d).mkdir(parents=True)
    return vault


def test_inbox_fallback_apply(tmp_path: Path):
    vault = _seed_vault(tmp_path)

    result = create_note(
        CreateInputs(title="Test Thing", type="project"),
        vault=vault,
        apply=True,
        today="2026-01-02",
    )

    dest = vault / "inbox" / "Test Thing.md"
    assert result.ok
    assert result.written
    assert dest.exists()
    text = dest.read_text(encoding="utf-8")
    assert "type: project" in text
    assert "supports:" not in text
    assert "quest: none" in text

"""Tests for ``pqn-quests`` markdown rendering."""

from __future__ import annotations

from para_quest_notes.workflows.quests.contract import (
    NoteEntry,
    QuestIndex,
    QuestRef,
)
from para_quest_notes.workflows.quests.render import render_markdown


def _index(*, scope=None) -> QuestIndex:
    return QuestIndex(
        vault="/v",
        scope=scope or {"types": None, "quest": None, "include_archive": False},
        quests=[
            QuestRef(name="Health", quest_kind="main"),
            QuestRef(name="Maintain Home", quest_kind="side"),
        ],
        notes=[
            NoteEntry("areas/Health.md", "Health", "area", "main", ["Health"], ["Health"]),
            NoteEntry(
                "areas/Maintain Home.md",
                "Maintain Home",
                "area",
                "side",
                ["Health"],
                ["Health"],
            ),
            NoteEntry("areas/Org.md", "Org", "area", "none", ["Health"], [], capability=True),
            NoteEntry("areas/Orphan.md", "Orphan", "area", "none", [], [], unassigned=True),
        ],
    )


def test_render_orders_main_then_side_then_capabilities_then_unassigned():
    out = render_markdown(_index())
    assert out.endswith("\n")
    # Section order.
    assert out.index("## [[Health]]") < out.index("## [[Maintain Home]]")
    assert out.index("## [[Maintain Home]]") < out.index("## Capabilities")
    assert out.index("## Capabilities") < out.index("## Unassigned")
    assert "- [[Org]] (area)" in out
    assert "- [[Orphan]] (area)" in out


def test_bullets_label_quest_kind():
    out = render_markdown(_index())
    # Quest notes are labeled by their kind, not their PARA type.
    assert "- [[Health]] (main quest)" in out
    assert "- [[Maintain Home]] (side quest)" in out
    # Non-quest notes keep their PARA type.
    assert "- [[Org]] (area)" in out


def test_capability_not_listed_under_quest_section():
    out = render_markdown(_index())
    health_block = out.split("## [[Health]]", 1)[1].split("##", 1)[0]
    assert "[[Org]]" not in health_block


def test_quest_filter_shows_only_that_section():
    scope = {"types": None, "quest": "health", "include_archive": False}
    out = render_markdown(_index(scope=scope))
    assert "## [[Health]]" in out
    assert "## [[Maintain Home]]" not in out
    assert "## Capabilities" not in out
    assert "## Unassigned" not in out

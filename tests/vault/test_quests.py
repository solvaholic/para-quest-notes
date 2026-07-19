"""Tests for vault Quest discovery."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from para_quest_notes.vault.frontmatter import LegacyQuestKeyWarning
from para_quest_notes.vault.quests import discover_quests, resolve_quest_from_path


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_discovers_main_and_side(tmp_path: Path):
    _write(
        tmp_path / "areas/Health.md",
        "---\ntype: area\nquest-kind: main\nsupports: ['[[Health]]']\n---\n",
    )
    _write(
        tmp_path / "areas/Maintain Home.md",
        "---\ntype: area\nquest-kind: side\nsupports: ['[[Health]]', '[[Create]]']\n---\n",
    )
    _write(tmp_path / "areas/Garden.md", "---\ntype: area\nquest-kind: none\n---\n")
    _write(tmp_path / "projects/Foo.md", "---\ntype: project\nquest-kind: main\n---\n")

    quests = discover_quests(tmp_path)
    names = [(q.name, q.quest_kind) for q in quests]
    assert names == [("Health", "main"), ("Maintain Home", "side")]
    assert quests[1].supports == ("Health", "Create")


def test_no_areas_dir(tmp_path: Path):
    assert discover_quests(tmp_path) == []


def test_discovers_legacy_quest_key_with_warning(tmp_path: Path):
    """A legacy ``quest:`` classifier is tolerated on read but warns (#98)."""
    _write(
        tmp_path / "areas/Health.md",
        "---\ntype: area\nquest: main\nsupports: ['[[Health]]']\n---\n",
    )
    with pytest.warns(LegacyQuestKeyWarning):
        quests = discover_quests(tmp_path)
    assert [(q.name, q.quest_kind) for q in quests] == [("Health", "main")]


def test_canonical_quest_kind_does_not_warn(tmp_path: Path):
    _write(
        tmp_path / "areas/Health.md",
        "---\ntype: area\nquest-kind: main\nsupports: ['[[Health]]']\n---\n",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", LegacyQuestKeyWarning)
        quests = discover_quests(tmp_path)
    assert [q.name for q in quests] == ["Health"]


def test_discovers_backmatter_quest(tmp_path: Path):
    """Legacy notes with quest:/supports: in tail backmatter are still found.

    Backmatter is tolerated on read (see docs/PLAN.md, "Open questions —
    decided 2026-05-12"). Without this, fresh vaults whose Quest notes
    pre-date the frontmatter-canonical decision can't be ingested - their
    Quests are invisible to pick_quest.
    """
    _write(
        tmp_path / "areas/Sustain.md",
        (
            "# Sustain\n\nBody copy.\n\n"
            "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Sustain]]'\n---\n"
        ),
    )
    quests = discover_quests(tmp_path)
    assert [(q.name, q.quest_kind) for q in quests] == [("Sustain", "main")]
    assert quests[0].supports == ("Sustain",)


def test_frontmatter_wins_over_backmatter(tmp_path: Path):
    _write(
        tmp_path / "areas/Health.md",
        (
            "---\ntype: area\nquest-kind: main\n---\n# Health\n\n"
            "Body.\n\n---\ntype: area\nquest-kind: side\n---\n"
        ),
    )
    quests = discover_quests(tmp_path)
    assert [(q.name, q.quest_kind) for q in quests] == [("Health", "main")]


# ---- resolve_quest_from_path (#47) --------------------------------------


def test_resolve_area_note_hit(tmp_path: Path):
    """Same-named Area note with supports: resolves the Quest."""
    _write(
        tmp_path / "areas/Health.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n# Health\n",
    )
    result = resolve_quest_from_path(tmp_path, "Health.md", valid_quests={"Health"})
    assert result.quests == ["Health"]
    assert result.source == "area_note"


def test_resolve_area_note_snake_case_match(tmp_path: Path):
    """Match key is normalized to snake_case before comparing to area stems."""
    _write(
        tmp_path / "areas/Maintain Home.md",
        "---\ntype: area\nquest-kind: side\nsupports:\n- '[[Health]]'\n---\n",
    )
    result = resolve_quest_from_path(tmp_path, "maintain_home.md", valid_quests={"Health"})
    assert result.quests == ["Health"]
    assert result.source == "area_note"


def test_resolve_area_note_wins_over_sibling(tmp_path: Path):
    """Same-named Area note wins even when sibling consensus differs."""
    _write(
        tmp_path / "areas/Health.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n",
    )
    # Sibling notes in projects/ all support Create
    _write(
        tmp_path / "projects/A.md",
        "---\ntype: project\nsupports:\n- '[[Create]]'\n---\n# A\n",
    )
    _write(
        tmp_path / "projects/B.md",
        "---\ntype: project\nsupports:\n- '[[Create]]'\n---\n# B\n",
    )
    result = resolve_quest_from_path(
        tmp_path, "projects/Health.md", valid_quests={"Health", "Create"}
    )
    assert result.quests == ["Health"]
    assert result.source == "area_note"


def test_resolve_sibling_consensus_hit(tmp_path: Path):
    """When no matching Area note, sibling consensus resolves the Quest."""
    _write(
        tmp_path / "projects/A.md",
        "---\ntype: project\nsupports:\n- '[[Create]]'\n---\n# A\n",
    )
    _write(
        tmp_path / "projects/B.md",
        "---\ntype: project\nsupports:\n- '[[Create]]'\n---\n# B\n",
    )
    _write(
        tmp_path / "projects/C.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\n# C\n",
    )
    result = resolve_quest_from_path(
        tmp_path, "projects/NewNote.md", valid_quests={"Create", "Health"}
    )
    assert result.quests == ["Create"]
    assert result.source == "sibling_consensus"


def test_resolve_sibling_consensus_no_majority(tmp_path: Path):
    """No clear majority among siblings results in a miss."""
    _write(
        tmp_path / "projects/A.md",
        "---\ntype: project\nsupports:\n- '[[Create]]'\n---\n# A\n",
    )
    _write(
        tmp_path / "projects/B.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\n# B\n",
    )
    result = resolve_quest_from_path(
        tmp_path, "projects/NewNote.md", valid_quests={"Create", "Health"}
    )
    assert result.quests == []
    assert result.source == "miss"


def test_resolve_miss_no_matching_area(tmp_path: Path):
    """No matching Area note and no siblings yields a miss."""
    _write(
        tmp_path / "areas/Health.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n",
    )
    result = resolve_quest_from_path(tmp_path, "projects/Unrelated.md", valid_quests={"Health"})
    assert result.quests == []
    assert result.source == "miss"


def test_resolve_filters_to_valid_quests(tmp_path: Path):
    """Area note supports: values not in valid_quests are filtered out."""
    _write(
        tmp_path / "areas/Foo.md",
        "---\ntype: area\nquest-kind: side\nsupports:\n- '[[Bogus]]'\n---\n",
    )
    result = resolve_quest_from_path(tmp_path, "Foo.md", valid_quests={"Health"})
    # Bogus is not valid, so it's a miss
    assert result.quests == []
    assert result.source == "miss"


def test_resolve_bare_basename(tmp_path: Path):
    """A bare basename (no directory) still matches an Area note."""
    _write(
        tmp_path / "areas/Create.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Create]]'\n---\n",
    )
    result = resolve_quest_from_path(tmp_path, "Create.md", valid_quests={"Create"})
    assert result.quests == ["Create"]
    assert result.source == "area_note"

"""Tests for the ``pqn-quests`` index builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.workflows.quests.builder import build_quest_index


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _fm(**pairs: str) -> str:
    lines = ["---"]
    for key, value in pairs.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines) + "\n"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A small but representative vault.

    Quests: Health (main), Create (main), Maintain Home (side -> Health,Create).
    Areas/Projects with supports, one Capability, resources reached only via
    incoming Area/Project links, plus inbox + daily notes that must be ignored.
    """
    # Main + Side Quest notes (self-support / serve).
    write(
        tmp_path / "areas" / "Health.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n# Health\n",
    )
    write(
        tmp_path / "areas" / "Create.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Create]]'\n---\n# Create\n",
    )
    write(
        tmp_path / "areas" / "Maintain Home.md",
        "---\ntype: area\nquest-kind: side\nsupports:\n- '[[Health]]'\n- '[[Create]]'\n---\n# MH\n",
    )
    # Plain Area supporting a Quest, and linking a Resource.
    write(
        tmp_path / "areas" / "Kitchen.md",
        "---\ntype: area\nsupports:\n- '[[Health]]'\n---\n# Kitchen\n\nSee [[Sourdough Notes]].\n",
    )
    # Project supporting a Quest, linking a Resource.
    write(
        tmp_path / "projects" / "Run a 5K.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\n# 5K\n\nUses [[Trail Map]].\n",
    )
    # Capability Area (own section, not under a Quest group).
    write(
        tmp_path / "areas" / "Be Organized.md",
        "---\ntype: area\ncapability: true\nsupports:\n- '[[Health]]'\n---\n# Org\n",
    )
    # Area with no supports -> Unassigned.
    write(tmp_path / "areas" / "Orphan Area.md", "---\ntype: area\n---\n# Orphan\n")
    # Resources: one linked (assigned), one linked-but-only-by-daily (unassigned),
    # one totally orphaned (unassigned).
    write(tmp_path / "resources" / "Sourdough Notes.md", "# Sourdough\n")
    write(tmp_path / "resources" / "Trail Map.md", "# Trail\n")
    write(tmp_path / "resources" / "Orphan Resource.md", "# Orphan res\n")
    # Daily note links a Resource — must NOT confer assignment.
    write(
        tmp_path / "resources" / "daily_notes" / "2026" / "02" / "2026-02-08.md",
        "# Day\n\nLinked [[Orphan Resource]].\n",
    )
    # Inbox note — out of scope entirely.
    write(tmp_path / "inbox" / "capture.md", "---\ntype: area\nsupports:\n- '[[Health]]'\n---\n")
    return tmp_path


def _titles_under(index, quest: str) -> set[str]:
    return {n.title for n in index.notes_for_quest(quest)}


def test_quests_discovered_in_order(vault: Path):
    index = build_quest_index(vault)
    # Main Quests (alpha) first, then Side Quests.
    assert [(q.name, q.quest_kind) for q in index.quests] == [
        ("Create", "main"),
        ("Health", "main"),
        ("Maintain Home", "side"),
    ]


def test_areas_and_projects_group_under_supports(vault: Path):
    index = build_quest_index(vault)
    health = _titles_under(index, "Health")
    assert {"Health", "Maintain Home", "Kitchen", "Run a 5K"} <= health
    # Multi-support note appears under both.
    assert "Maintain Home" in _titles_under(index, "Create")


def test_capability_gets_own_section_not_quest_group(vault: Path):
    index = build_quest_index(vault)
    assert {n.title for n in index.capabilities} == {"Be Organized"}
    # Not duplicated under the Quest it supports.
    assert "Be Organized" not in _titles_under(index, "Health")


def test_resource_assigned_via_active_area_project_link(vault: Path):
    index = build_quest_index(vault)
    assert "Sourdough Notes" in _titles_under(index, "Health")
    assert "Trail Map" in _titles_under(index, "Health")


def test_daily_note_link_does_not_assign_resource(vault: Path):
    index = build_quest_index(vault)
    unassigned = {n.title for n in index.unassigned}
    assert "Orphan Resource" in unassigned


def test_unassigned_collects_untagged_areas_and_orphan_resources(vault: Path):
    index = build_quest_index(vault)
    unassigned = {n.title for n in index.unassigned}
    assert "Orphan Area" in unassigned
    assert "Orphan Resource" in unassigned


def test_inbox_and_daily_notes_excluded(vault: Path):
    index = build_quest_index(vault)
    paths = {n.path for n in index.notes}
    assert not any(p.startswith("inbox/") for p in paths)
    assert not any("daily_notes" in p for p in paths)


def test_type_filter_is_include_only(vault: Path):
    index = build_quest_index(vault, types=["project"])
    assert {n.type for n in index.notes} == {"project"}
    # Excluding 'area' drops Capabilities.
    assert index.capabilities == []


def test_quest_filter_restricts_to_matching_notes(vault: Path):
    index = build_quest_index(vault, quest="[[Health]]")
    # Every retained note either rolls up to Health or declares it in supports
    # (capabilities support a Quest but carry an empty rollup by design).
    for note in index.notes:
        rolled = "health" in [q.lower() for q in note.quests]
        declared = "health" in [s.lower() for s in note.supports]
        assert rolled or declared
    assert index.unassigned == []


def test_json_contract_shape(vault: Path):
    data = build_quest_index(vault).to_dict()
    assert set(data) == {"vault", "scope", "summary", "quests", "notes"}
    assert set(data["summary"]) == {"quests", "notes", "capabilities", "unassigned"}
    # Each note appears exactly once (flat).
    paths = [n["path"] for n in data["notes"]]
    assert len(paths) == len(set(paths))


def test_include_archive_toggles_archived_notes(vault: Path):
    write(
        vault / "archive" / "projects" / "Done.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\n# Done\n",
    )
    default = build_quest_index(vault)
    assert "Done" not in _titles_under(default, "Health")

    with_archive = build_quest_index(vault, include_archive=True)
    assert "Done" in _titles_under(with_archive, "Health")


def test_archived_area_does_not_assign_resource(vault: Path):
    # An archived Project links a fresh resource; even with --include-archive,
    # archived notes are not "active" and must not confer assignment.
    write(
        vault / "archive" / "projects" / "Old Project.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\n[[Museum Pamphlet]]\n",
    )
    write(vault / "resources" / "Museum Pamphlet.md", "# Pamphlet\n")
    index = build_quest_index(vault, include_archive=True)
    assert "Museum Pamphlet" in {n.title for n in index.unassigned}

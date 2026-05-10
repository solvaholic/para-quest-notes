"""Tests for vault Quest discovery."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.workflows.ingest_inbox.vault_quests import discover_quests


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_discovers_main_and_side(tmp_path: Path):
    _write(
        tmp_path / "areas/Health.md",
        "---\ntype: area\nquest: main\nsupports: ['[[Health]]']\n---\n",
    )
    _write(
        tmp_path / "areas/Maintain Home.md",
        "---\ntype: area\nquest: side\nsupports: ['[[Health]]', '[[Create]]']\n---\n",
    )
    _write(tmp_path / "areas/Garden.md", "---\ntype: area\nquest: none\n---\n")
    _write(tmp_path / "projects/Foo.md", "---\ntype: project\nquest: main\n---\n")

    quests = discover_quests(tmp_path)
    names = [(q.name, q.quest_kind) for q in quests]
    assert names == [("Health", "main"), ("Maintain Home", "side")]
    assert quests[1].supports == ("Health", "Create")


def test_no_areas_dir(tmp_path: Path):
    assert discover_quests(tmp_path) == []

"""Tests for ``seeds.yaml`` parsing and reference validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from para_quest_notes.corpus.seeds import SeedsError, load_seeds


def test_bundled_seeds_load() -> None:
    seeds = load_seeds()
    assert seeds.main_quests, "expected at least one Main Quest"
    assert seeds.side_quests
    assert seeds.areas
    assert seeds.projects
    assert seeds.resources
    assert seeds.task_verbs
    assert seeds.topic_dirs
    assert seeds.obsidian_tags


def test_bundled_seeds_have_no_dangling_refs() -> None:
    # load_seeds() runs the validator; this is a belt-and-suspenders
    # assertion in case the validator gets accidentally relaxed.
    seeds = load_seeds()
    main = seeds.main_quest_names
    quests = seeds.quest_names
    areas = seeds.area_names
    for sq in seeds.side_quests:
        assert sq.supports
        for ref in sq.supports:
            assert ref in main, f"side quest {sq.name} -> unknown main {ref}"
    for area in seeds.areas:
        for ref in area.supports:
            assert ref in quests
    for project in seeds.projects:
        assert project.supports
        for ref in project.supports:
            assert ref in quests
    for resource in seeds.resources:
        for ref in resource.parents:
            assert ref in areas


def test_dangling_side_quest_ref_raises(tmp_path: Path) -> None:
    bad = tmp_path / "seeds.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "main_quests": [{"name": "Health", "purpose": "p"}],
                "side_quests": [{"name": "X", "supports": ["DoesNotExist"]}],
                "areas": [],
                "projects": [{"title": "P", "supports": ["Health"]}],
                "resources": [],
                "task_verbs": ["Do"],
                "topic_dirs": ["Misc"],
                "obsidian_tags": ["t"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SeedsError, match="DoesNotExist"):
        load_seeds(bad)


def test_project_without_supports_raises(tmp_path: Path) -> None:
    bad = tmp_path / "seeds.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "main_quests": [{"name": "Health", "purpose": "p"}],
                "side_quests": [],
                "areas": [],
                "projects": [{"title": "P", "supports": []}],
                "resources": [],
                "task_verbs": ["Do"],
                "topic_dirs": ["Misc"],
                "obsidian_tags": ["t"],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(SeedsError, match="must support"):
        load_seeds(bad)


def test_top_level_must_be_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "seeds.yaml"
    bad.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(SeedsError, match="mapping"):
        load_seeds(bad)

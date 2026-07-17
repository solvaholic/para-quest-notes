"""Tests for :mod:`para_quest_notes.vault.scope`."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.vault.scope import (
    Scope,
    note_supports,
    para_type_of,
    strip_wikilink,
)


def test_strip_wikilink_handles_alias_and_plain():
    assert strip_wikilink("[[Health]]") == "Health"
    assert strip_wikilink("[[Health|my health]]") == "Health"
    assert strip_wikilink("  Health  ") == "Health"


def test_note_supports_normalizes_list_and_scalar():
    assert note_supports({"supports": ["[[Health]]", "[[Create]]"]}) == ["Health", "Create"]
    assert note_supports({"supports": "[[Health]]"}) == ["Health"]
    assert note_supports({}) == []


def test_para_type_prefers_frontmatter(tmp_path: Path):
    p = tmp_path / "misc" / "Note.md"
    assert para_type_of(tmp_path, p, {"type": "project"}) == "project"


def test_para_type_falls_back_to_top_level_dir(tmp_path: Path):
    assert para_type_of(tmp_path, tmp_path / "areas" / "A.md", {}) == "area"
    assert para_type_of(tmp_path, tmp_path / "projects" / "P.md", {}) == "project"
    assert para_type_of(tmp_path, tmp_path / "resources" / "R.md", {}) == "resource"
    assert para_type_of(tmp_path, tmp_path / "misc" / "X.md", {}) is None


def test_para_type_looks_past_archive_segment(tmp_path: Path):
    p = tmp_path / "archive" / "projects" / "Old.md"
    assert para_type_of(tmp_path, p, {}) == "project"


def test_scope_type_is_include_only():
    scope = Scope.from_args(types=["area"])
    assert scope.allows_type("area")
    assert not scope.allows_type("project")
    assert not scope.allows_type(None)

    unscoped = Scope.from_args()
    assert unscoped.allows_type("resource")
    assert unscoped.allows_type(None)


def test_scope_quest_matches_supports():
    scope = Scope.from_args(quest="[[Health]]")
    assert scope.matches_quest(["Create", "Health"])
    assert not scope.matches_quest(["Create"])
    assert not scope.matches_quest([])

    assert Scope.from_args().matches_quest([])  # no filter -> always matches

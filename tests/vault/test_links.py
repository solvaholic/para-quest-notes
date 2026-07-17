"""Tests for :mod:`para_quest_notes.vault.links`."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.vault.links import (
    build_backlink_index,
    link_targets,
    scan_backlinks,
)


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_link_targets_extracts_stem_ignoring_anchor_and_alias():
    text = "See [[Water Heater Models]], [[Health#Goals]], and [[Health|my health]]."
    assert link_targets(text) == ["Water Heater Models", "Health", "Health"]


def test_scan_backlinks_counts_and_excludes_source(tmp_path: Path):
    write(tmp_path / "areas" / "A.md", "links [[Target]] and again [[target]]")
    src = write(tmp_path / "areas" / "Target.md", "self [[Target]]")
    write(tmp_path / "projects" / "B.md", "no link here")

    hits = scan_backlinks(tmp_path, "Target", exclude=src)
    assert hits == [{"file": "areas/A.md", "occurrences": 2}]


def test_scan_backlinks_excludes_archive_by_default(tmp_path: Path):
    write(tmp_path / "archive" / "old.md", "[[Target]]")
    write(tmp_path / "areas" / "A.md", "[[Target]]")

    default = scan_backlinks(tmp_path, "Target")
    assert [h["file"] for h in default] == ["areas/A.md"]

    with_archive = scan_backlinks(tmp_path, "Target", include_archive=True)
    assert {h["file"] for h in with_archive} == {"areas/A.md", "archive/old.md"}


def test_build_backlink_index_maps_target_to_sources(tmp_path: Path):
    a = write(tmp_path / "areas" / "A.md", "[[Resource]] [[Resource]] [[Other]]")
    b = write(tmp_path / "projects" / "B.md", "[[resource]]")

    index = build_backlink_index([a, b])
    sources = {bl.source: bl.occurrences for bl in index.sources_for("Resource")}
    assert sources == {a: 2, b: 1}
    assert index.sources_for("missing") == []

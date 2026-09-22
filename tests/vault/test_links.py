"""Tests for :mod:`para_quest_notes.vault.links`."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from unicodedata import normalize

import pytest

from para_quest_notes.vault.links import (
    LinkTargetError,
    build_backlink_index,
    build_link_graph,
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


def test_build_backlink_index_keeps_generator_and_path_compatibility(tmp_path: Path):
    a = write(tmp_path / "areas" / "A.md", "[[Resource]]")
    b = write(tmp_path / "projects" / "B.md", "[[Resource]]")

    index = build_backlink_index(path for path in (a, b))

    assert [backlink.source for backlink in index.sources_for("Resource")] == [a, b]


def test_link_graph_tracks_directional_counts_and_unresolved_targets(tmp_path: Path):
    a = write(
        tmp_path / "areas" / "A.md",
        "[[B]] ![[projects/B.md#Section|alias]] [[Missing]] [[missing]] [[Duplicate]] [[A]]",
    )
    b = write(tmp_path / "projects" / "B.md", "[[A]] [[a|again]]")
    duplicate_a = write(tmp_path / "resources" / "one" / "Duplicate.md", "")
    duplicate_b = write(tmp_path / "resources" / "two" / "Duplicate.md", "")

    graph = build_link_graph(tmp_path, [a, b, duplicate_a, duplicate_b])
    note_a = graph.resolve_target("a.md")
    note_b = graph.resolve_target("projects/B.md")

    assert [
        (edge.target.relative_path, edge.occurrences) for edge in graph.outgoing_from(note_a)
    ] == [
        ("areas/A.md", 1),
        ("projects/B.md", 2),
    ]
    assert [
        (edge.source.relative_path, edge.occurrences) for edge in graph.incoming_to(note_a)
    ] == [
        ("areas/A.md", 1),
        ("projects/B.md", 2),
    ]
    assert [
        (item.target, item.occurrences, item.reason, list(item.candidates))
        for item in graph.unresolved_from(note_a)
    ] == [
        (
            "Duplicate",
            1,
            "ambiguous",
            [
                "resources/one/Duplicate.md",
                "resources/two/Duplicate.md",
            ],
        ),
        ("Missing", 2, "missing", []),
    ]
    assert note_b.text == "[[A]] [[a|again]]"


def test_link_graph_target_resolution_is_safe_and_typed(tmp_path: Path):
    first = write(tmp_path / "areas" / "First.md", "")
    duplicate_a = write(tmp_path / "projects" / "one" / "Duplicate.md", "")
    duplicate_b = write(tmp_path / "resources" / "two" / "Duplicate.md", "")
    graph = build_link_graph(tmp_path, [first, duplicate_a, duplicate_b])

    assert graph.resolve_target("FIRST").relative_path == "areas/First.md"
    assert graph.resolve_target("first.md").relative_path == "areas/First.md"
    assert graph.resolve_target("areas/First.md").relative_path == "areas/First.md"

    with pytest.raises(LinkTargetError) as missing:
        graph.resolve_target("Missing")
    assert missing.value.kind == "missing"

    with pytest.raises(LinkTargetError) as ambiguous:
        graph.resolve_target("duplicate")
    assert ambiguous.value.kind == "ambiguous"
    assert ambiguous.value.candidates == (
        "projects/one/Duplicate.md",
        "resources/two/Duplicate.md",
    )

    with pytest.raises(LinkTargetError) as escaped:
        graph.resolve_target("../First.md")
    assert escaped.value.kind == "outside_vault"


def test_link_graph_prefers_an_exact_root_path_over_an_ambiguous_basename(
    tmp_path: Path,
):
    root = write(tmp_path / "Duplicate.md", "")
    nested = write(tmp_path / "areas" / "Duplicate.md", "")
    graph = build_link_graph(tmp_path, [root, nested])

    assert graph.resolve_target("Duplicate.md").relative_path == "Duplicate.md"
    with pytest.raises(LinkTargetError) as ambiguous:
        graph.resolve_target("Duplicate")
    assert ambiguous.value.candidates == ("Duplicate.md", "areas/Duplicate.md")


def test_link_graph_resolves_path_qualified_wikilinks_without_inventing_edges(
    tmp_path: Path,
):
    source = write(
        tmp_path / "areas" / "Source.md",
        "[[resources/one/Duplicate.md]] [[resources/one/Duplicate|again]]",
    )
    first = write(tmp_path / "resources" / "one" / "Duplicate.md", "")
    second = write(tmp_path / "resources" / "two" / "Duplicate.md", "")
    graph = build_link_graph(tmp_path, [source, first, second])

    edge = graph.outgoing_from(graph.resolve_target("Source"))[0]
    assert edge.target.relative_path == "resources/one/Duplicate.md"
    assert edge.occurrences == 2
    assert graph.unresolved_from(graph.resolve_target("Source")) == ()


def test_link_graph_normalizes_unicode_case_and_backslash_paths(tmp_path: Path):
    decomposed = normalize("NFD", "Café")
    note = write(tmp_path / "areas" / f"{decomposed}.md", "")
    graph = build_link_graph(tmp_path, [note])

    assert graph.resolve_target("CAFÉ").relative_path == f"areas/{decomposed}.md"
    assert graph.resolve_target(r"areas\Café.md").relative_path == (f"areas/{decomposed}.md")
    with pytest.raises(LinkTargetError) as escaped:
        graph.resolve_target(r"..\Café.md")
    assert escaped.value.kind == "outside_vault"


def test_link_graph_reads_each_candidate_at_most_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    files = [
        write(tmp_path / "areas" / "A.md", "[[B]]"),
        write(tmp_path / "projects" / "B.md", "[[A]]"),
    ]
    real_read = Path.read_text
    reads: Counter[Path] = Counter()

    def counting_read(path: Path, *args: object, **kwargs: object) -> str:
        reads[path] += 1
        return real_read(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", counting_read)
    graph = build_link_graph(tmp_path, files)

    assert graph.resolve_target("A").relative_path == "areas/A.md"
    assert reads == Counter({files[0]: 1, files[1]: 1})


def test_link_graph_handles_symlink_equivalent_vault_and_file_paths(tmp_path: Path):
    real_vault = tmp_path / "real-vault"
    note = write(real_vault / "areas" / "A.md", "")
    alias_vault = tmp_path / "alias-vault"
    alias_vault.symlink_to(real_vault, target_is_directory=True)

    graph = build_link_graph(alias_vault, [note.resolve()])

    resolved = graph.resolve_target("A")
    assert resolved.relative_path == "areas/A.md"
    assert resolved.path == alias_vault.absolute() / "areas" / "A.md"

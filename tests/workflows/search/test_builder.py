"""Tests for the ``pqn-search`` builder (matching, scope, ranking)."""

from __future__ import annotations

from pathlib import Path

import pytest

from para_quest_notes.workflows.search.builder import search


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    write(
        tmp_path / "areas" / "Health.md",
        "---\ntype: area\nquest-kind: main\nsupports:\n- '[[Health]]'\n---\n# Health\n",
    )
    write(
        tmp_path / "projects" / "Run a 5K.md",
        "---\ntype: project\nsupports:\n- '[[Health]]'\n---\nTraining plan for the 5K race.\n",
    )
    write(
        tmp_path / "resources" / "Running Shoes.md",
        "---\ntype: resource\n---\nNotes on running shoes and gear.\n",
    )
    # Two active notes link to the resource -> inbound count 2.
    write(
        tmp_path / "resources" / "Race Day.md",
        "---\ntype: resource\n---\nWear the right [[Running Shoes]] for the race.\n",
    )
    write(
        tmp_path / "resources" / "daily_notes" / "2026-05-01.md",
        "Bought new [[Running Shoes]] today for running.\n",
    )
    return tmp_path


def test_matches_title_and_body_by_default(vault: Path):
    results = search(vault, ["running"])
    paths = {r.path for r in results.results}
    # "running" is in the Running Shoes title and the daily-note body.
    assert "resources/Running Shoes.md" in paths
    assert "resources/daily_notes/2026-05-01.md" in paths


def test_title_scope_excludes_body_only_hits(vault: Path):
    results = search(vault, ["training"], title=True)
    # "training" only appears in a body, not any title.
    assert results.results == []


def test_content_scope_matches_body(vault: Path):
    results = search(vault, ["training"], content=True)
    assert [r.path for r in results.results] == ["projects/Run a 5K.md"]
    assert results.results[0].match_context.where == "body"
    assert "training" in results.results[0].match_context.snippet.lower()


def test_and_semantics_across_keywords(vault: Path):
    # "running" appears in the daily note; "gear" only in Running Shoes body.
    both = search(vault, ["running", "gear"])
    assert [r.path for r in both.results] == ["resources/Running Shoes.md"]


def test_title_hits_rank_before_body_hits(vault: Path):
    results = search(vault, ["running"])
    wheres = [r.match_context.where for r in results.results]
    # Every title hit precedes every body hit.
    assert wheres == sorted(wheres, key=lambda w: 0 if w == "title" else 1)
    assert results.results[0].match_context.where == "title"


def test_resource_ranked_by_inbound_links(vault: Path):
    # Both resources match "running" in their title/body; Running Shoes has
    # two inbound links (Race Day + daily note), Race Day has none.
    write(
        vault / "resources" / "Running Log.md",
        "---\ntype: resource\n---\nA log.\n",
    )
    results = search(vault, ["running"], types=["resource"])
    resource_paths = [r.path for r in results.results]
    assert resource_paths[0] == "resources/Running Shoes.md"
    shoes = next(r for r in results.results if r.path == "resources/Running Shoes.md")
    assert shoes.incoming_links == 2


def test_type_filter_include_only(vault: Path):
    results = search(vault, ["running"], types=["resource"])
    assert {r.type for r in results.results} == {"resource"}


def test_quest_filter_matches_supports(vault: Path):
    # A resource mentions "health" but declares no supports; the Area does.
    write(
        vault / "resources" / "Health Tips.md",
        "---\ntype: resource\n---\nGeneral health advice.\n",
    )
    unfiltered = {r.path for r in search(vault, ["health"]).results}
    assert unfiltered == {"areas/Health.md", "resources/Health Tips.md"}

    filtered = search(vault, ["health"], quest="[[Health]]")
    # Only the Area supports [[Health]]; the resource is filtered out.
    assert [r.path for r in filtered.results] == ["areas/Health.md"]


def test_limit_caps_results(vault: Path):
    results = search(vault, ["running"], limit=1)
    assert len(results.results) == 1


def test_archive_excluded_by_default(vault: Path):
    write(
        vault / "archive" / "resources" / "Old Running Notes.md",
        "---\ntype: resource\n---\nAncient running notes.\n",
    )
    default = search(vault, ["running"])
    assert all("archive/" not in r.path for r in default.results)
    included = search(vault, ["running"], include_archive=True)
    assert any("archive/" in r.path for r in included.results)


def test_archive_links_do_not_count(vault: Path):
    # An archived note links to Running Shoes; it must not raise the count.
    write(
        vault / "archive" / "resources" / "Old Gear.md",
        "---\ntype: resource\n---\nUsed [[Running Shoes]] back then.\n",
    )
    shoes = next(
        r for r in search(vault, ["running"]).results if r.path == "resources/Running Shoes.md"
    )
    # Still just the two active linkers (Race Day + daily note).
    assert shoes.incoming_links == 2


def test_scope_echoed_in_results(vault: Path):
    results = search(vault, ["running"], types=["resource"], limit=5)
    assert results.scope["types"] == ["resource"]
    assert results.scope["limit"] == 5
    assert results.scope["title"] is True
    assert results.scope["content"] is True


def test_snippet_radius_controls_body_window(vault: Path):
    wide = search(vault, ["training"], content=True, snippet_radius=80)
    narrow = search(vault, ["training"], content=True, snippet_radius=15)
    wide_snip = wide.results[0].match_context.snippet
    narrow_snip = narrow.results[0].match_context.snippet
    assert "training" in wide_snip.lower()
    assert "training" in narrow_snip.lower()
    assert len(narrow_snip) < len(wide_snip)


def test_snippet_radius_zero_suppresses_body_snippet(vault: Path):
    results = search(vault, ["training"], content=True, snippet_radius=0)
    hit = results.results[0]
    assert hit.match_context.where == "body"
    assert hit.match_context.snippet == ""


def test_snippet_radius_zero_suppresses_title_snippet(vault: Path):
    results = search(vault, ["running"], title=True, snippet_radius=0)
    shoes = next(r for r in results.results if r.path == "resources/Running Shoes.md")
    assert shoes.match_context.where == "title"
    assert shoes.match_context.snippet == ""


def test_snippet_radius_negative_clamps_to_zero(vault: Path):
    results = search(vault, ["training"], content=True, snippet_radius=-10)
    assert results.results[0].match_context.snippet == ""
    assert results.scope["snippet_radius"] == 0


def test_snippet_radius_echoed_in_scope(vault: Path):
    results = search(vault, ["running"], snippet_radius=25)
    assert results.scope["snippet_radius"] == 25

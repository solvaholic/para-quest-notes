"""Tests for the ``pqn-search`` builder (matching, scope, ranking)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from para_quest_notes.workflows.search import MatchEvidence
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


def test_match_evidence_uses_distinct_keywords_in_first_query_order(vault: Path):
    result = search(vault, ["RUNNING", "gear", "running", "GEAR"]).results[0]

    assert [(match.keyword, match.where) for match in result.matches] == [
        ("RUNNING", "title"),
        ("gear", "body"),
    ]
    assert result.matches[0].snippet == "Running Shoes"
    assert "gear" in result.matches[1].snippet.lower()


def test_match_evidence_has_one_item_for_a_repeated_body_keyword(vault: Path):
    write(
        vault / "projects" / "Repeated Occurrences.md",
        "---\ntype: project\n---\nThe evidence keyword appears twice: evidence.\n",
    )

    hit = next(
        result
        for result in search(vault, ["evidence"]).results
        if result.path == "projects/Repeated Occurrences.md"
    )
    assert len(hit.matches) == 1
    assert hit.matches[0].keyword == "evidence"
    assert hit.matches[0].where == "body"


def test_match_evidence_records_title_body_and_mixed_hits(vault: Path):
    write(
        vault / "projects" / "Title Signal.md",
        "---\ntype: project\n---\nThe body has no matching term.\n",
    )
    write(
        vault / "projects" / "Body Only.md",
        "---\ntype: project\n---\nA body signal appears here.\n",
    )
    write(
        vault / "projects" / "Mixed Title Keyword.md",
        "---\ntype: project\n---\nA body signal appears here too.\n",
    )

    title = search(vault, ["signal"], title=True).results
    assert [result.matches[0].where for result in title] == ["title"]

    body = search(vault, ["signal"], content=True).results
    assert [result.matches[0].where for result in body] == ["body", "body"]

    mixed = next(
        result for result in search(vault, ["title", "signal"]).results if "Mixed" in result.path
    )
    assert [(match.keyword, match.where) for match in mixed.matches] == [
        ("title", "title"),
        ("signal", "body"),
    ]


def test_title_evidence_wins_when_a_keyword_appears_in_both_fields(vault: Path):
    write(
        vault / "projects" / "Both Signal.md",
        "---\ntype: project\n---\nA signal also appears in the body.\n",
    )

    hit = next(
        result for result in search(vault, ["signal"]).results if "Both Signal" in result.path
    )
    assert hit.matches == [MatchEvidence(keyword="signal", where="title", snippet="Both Signal")]
    assert hit.match_context.where == "title"


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
    assert wide.results[0].matches[0].snippet == wide_snip
    assert narrow.results[0].matches[0].snippet == narrow_snip


def test_snippet_radius_zero_suppresses_body_snippet(vault: Path):
    results = search(vault, ["training"], content=True, snippet_radius=0)
    hit = results.results[0]
    assert hit.match_context.where == "body"
    assert hit.match_context.snippet == ""
    assert hit.matches == [MatchEvidence(keyword="training", where="body", snippet="")]


def test_snippet_radius_zero_suppresses_title_snippet(vault: Path):
    results = search(vault, ["running"], title=True, snippet_radius=0)
    shoes = next(r for r in results.results if r.path == "resources/Running Shoes.md")
    assert shoes.match_context.where == "title"
    assert shoes.match_context.snippet == ""
    assert shoes.matches == [MatchEvidence(keyword="running", where="title", snippet="")]


def test_snippet_radius_negative_clamps_to_zero(vault: Path):
    results = search(vault, ["training"], content=True, snippet_radius=-10)
    assert results.results[0].match_context.snippet == ""
    assert results.scope["snippet_radius"] == 0


def test_snippet_radius_echoed_in_scope(vault: Path):
    results = search(vault, ["running"], snippet_radius=25)
    assert results.scope["snippet_radius"] == 25


def test_match_context_keeps_compatibility_selection_and_body_window(vault: Path):
    write(
        vault / "projects" / "Compatibility.md",
        "---\ntype: project\n---\nBeta appears first, then much later alpha appears.\n",
    )

    hit = next(
        result
        for result in search(vault, ["alpha", "beta"], content=True, snippet_radius=8).results
        if result.path == "projects/Compatibility.md"
    )
    assert [(match.keyword, match.where) for match in hit.matches] == [
        ("alpha", "body"),
        ("beta", "body"),
    ]
    assert hit.match_context.where == "body"
    assert hit.match_context.snippet == hit.matches[1].snippet


def test_content_search_includes_fenced_code_block_evidence(vault: Path):
    write(
        vault / "projects" / "Code Example.md",
        "---\ntype: project\n---\n```sh\nfenced-token\n```\n",
    )

    hit = next(
        result
        for result in search(vault, ["fenced-token"], content=True).results
        if "Code" in result.path
    )
    assert hit.matches[0].where == "body"
    assert "fenced-token" in hit.matches[0].snippet


def test_empty_results_and_output_are_deterministic(vault: Path):
    assert search(vault, ["zzzznotfound"]).results == []
    first = search(vault, ["running", "gear"]).to_dict()
    second = search(vault, ["running", "gear"]).to_dict()
    assert first == second


def test_search_sample_vault_copy_exposes_multikeyword_evidence(tmp_path: Path):
    sample = Path(__file__).resolve().parents[3] / "samples" / "vault"
    copied_vault = tmp_path / "vault"
    shutil.copytree(sample, copied_vault)
    write(
        copied_vault / "projects" / "Evidence Title Token.md",
        "---\ntype: project\n---\nEvidence body token is deliberately unique.\n",
    )

    hit = next(
        result
        for result in search(copied_vault, ["title", "body"]).results
        if result.path == "projects/Evidence Title Token.md"
    )
    assert [(match.keyword, match.where) for match in hit.matches] == [
        ("title", "title"),
        ("body", "body"),
    ]
    assert hit.match_context.where == "title"

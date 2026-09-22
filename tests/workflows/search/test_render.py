"""Tests for the ``pqn-search`` text renderer."""

from __future__ import annotations

from para_quest_notes.workflows.search.contract import (
    LinkContext,
    LinkSearchResult,
    LinkSearchResults,
    MatchContext,
    MatchEvidence,
    ResolvedLinkTarget,
    SearchResult,
    SearchResults,
    UnresolvedLink,
)
from para_quest_notes.workflows.search.render import render_link_text, render_text


def _results(*results: SearchResult) -> SearchResults:
    return SearchResults(vault="/v", query=["running"], results=list(results))


def test_empty_results():
    out = render_text(_results())
    assert "0 matches" in out
    assert "No matches." in out
    assert out.endswith("\n")


def test_singular_match_count():
    out = render_text(
        _results(
            SearchResult(
                path="resources/Running Shoes.md",
                type="resource",
                match_context=MatchContext(where="title", snippet="Running Shoes"),
            )
        )
    )
    assert "(1 match)" in out


def test_resource_shows_link_count_and_supports():
    out = render_text(
        _results(
            SearchResult(
                path="resources/Running Shoes.md",
                type="resource",
                supports=["Health"],
                match_context=MatchContext(where="title", snippet="Running Shoes"),
                incoming_links=2,
            )
        )
    )
    assert "resources/Running Shoes.md (resource, 2 links, supports: Health)" in out
    assert 'title: "Running Shoes"' in out


def test_body_hit_renders_snippet():
    out = render_text(
        _results(
            SearchResult(
                path="projects/Run a 5K.md",
                type="project",
                match_context=MatchContext(where="body", snippet="...a running plan..."),
            )
        )
    )
    assert 'body: "...a running plan..."' in out


def test_empty_snippet_omits_quoted_tail():
    out = render_text(
        _results(
            SearchResult(
                path="resources/Running Shoes.md",
                type="resource",
                match_context=MatchContext(where="title", snippet=""),
            )
        )
    )
    assert "resources/Running Shoes.md (resource) - title" in out
    assert '"' not in out.split("\n", 2)[-1]


def test_single_evidence_keeps_existing_text_shape():
    out = render_text(
        _results(
            SearchResult(
                path="resources/Running Shoes.md",
                type="resource",
                match_context=MatchContext(where="title", snippet="Running Shoes"),
                matches=[MatchEvidence(keyword="running", where="title", snippet="Running Shoes")],
            )
        )
    )
    assert out == (
        '# Search results for "running" (1 match)\n\n'
        '- resources/Running Shoes.md (resource) - title: "Running Shoes"\n'
    )


def test_multiple_evidence_names_each_keyword_and_location():
    out = render_text(
        _results(
            SearchResult(
                path="projects/Run a 5K.md",
                type="project",
                match_context=MatchContext(where="title", snippet="Run a 5K"),
                matches=[
                    MatchEvidence(keyword="run", where="title", snippet="Run a 5K"),
                    MatchEvidence(keyword="plan", where="body", snippet="...training plan..."),
                ],
            )
        )
    )
    assert 'matches: run (title): "Run a 5K"; plan (body): "...training plan..."' in out


def test_multiple_evidence_with_zero_radius_keeps_keywords_and_locations():
    out = render_text(
        _results(
            SearchResult(
                path="projects/Run a 5K.md",
                type="project",
                matches=[
                    MatchEvidence(keyword="run", where="title", snippet=""),
                    MatchEvidence(keyword="plan", where="body", snippet=""),
                ],
            )
        )
    )
    assert "matches: run (title); plan (body)" in out


def test_link_text_renders_target_neighbors_and_unresolved_links():
    results = LinkSearchResults(
        vault="/v",
        target=ResolvedLinkTarget(
            path="resources/Running Shoes.md",
            type="resource",
            supports=[],
        ),
        results=[
            LinkSearchResult(
                path="projects/Run a 5K.md",
                type="project",
                supports=["Health"],
                link_context=LinkContext(
                    relation="mutual",
                    outgoing_occurrences=1,
                    incoming_occurrences=2,
                ),
            )
        ],
        unresolved_links=[
            UnresolvedLink(
                target="Missing Note",
                occurrences=1,
                reason="missing",
            )
        ],
    )

    out = render_link_text(results)

    assert out.startswith('# Link neighbors for "resources/Running Shoes.md" (1 match)')
    assert (
        "- projects/Run a 5K.md (project, supports: Health) - mutual: outgoing 1, incoming 2"
    ) in out
    assert "## Unresolved outgoing links" in out
    assert "- Missing Note (missing, 1 occurrence)" in out
    assert out.endswith("\n")


def test_link_text_empty_neighborhood_is_successful():
    results = LinkSearchResults(
        vault="/v",
        target=ResolvedLinkTarget(
            path="areas/Alone.md",
            type="area",
            supports=[],
        ),
    )

    out = render_link_text(results)

    assert "(0 matches)" in out
    assert "No linked notes." in out

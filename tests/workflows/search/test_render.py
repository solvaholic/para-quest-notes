"""Tests for the ``pqn-search`` text renderer."""

from __future__ import annotations

from para_quest_notes.workflows.search.contract import (
    MatchContext,
    MatchEvidence,
    SearchResult,
    SearchResults,
)
from para_quest_notes.workflows.search.render import render_text


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

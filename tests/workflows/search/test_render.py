"""Tests for the ``pqn-search`` text renderer."""

from __future__ import annotations

from para_quest_notes.workflows.search.contract import (
    MatchContext,
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

"""Library entry points for ``pqn-search``.

Agents and other workflows call :func:`search` for keywords or
:func:`search_links` for direct link traversal rather than shelling out to the
CLI.
"""

from __future__ import annotations

from para_quest_notes.vault.links import LinkTargetError

from .builder import search, search_links
from .contract import (
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
from .render import render_link_text, render_text

__all__ = [
    "LinkContext",
    "LinkSearchResult",
    "LinkSearchResults",
    "LinkTargetError",
    "MatchContext",
    "MatchEvidence",
    "ResolvedLinkTarget",
    "SearchResult",
    "SearchResults",
    "UnresolvedLink",
    "render_link_text",
    "render_text",
    "search",
    "search_links",
]

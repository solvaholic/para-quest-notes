"""``pqn-search`` - keyword and direct-link search, PARA + Quest-aware.

Read-only, stateless, and no-LLM. Keyword mode matches notes by title or body.
Link mode resolves one target and reports its direct outgoing links and
incoming backlinks. See ``docs/workflows/search.md``.
"""

from para_quest_notes.workflows.search.api import (
    LinkContext,
    LinkSearchResult,
    LinkSearchResults,
    LinkTargetError,
    MatchContext,
    MatchEvidence,
    ResolvedLinkTarget,
    SearchResult,
    SearchResults,
    UnresolvedLink,
    render_link_text,
    render_text,
    search,
    search_links,
)

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

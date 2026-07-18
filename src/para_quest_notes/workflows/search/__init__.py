"""``pqn-search`` - keyword search over the vault, PARA + Quest-aware (no LLM).

Read-only and stateless: matches notes by title and/or body keywords, filters
by ``--type`` / ``--quest``, and ranks hits (title hits first; Resources
tie-broken by inbound-link count). Emits a flat list as text (default) or
JSON. See ``docs/workflows/search.md``.
"""

from para_quest_notes.workflows.search.api import (
    MatchContext,
    SearchResult,
    SearchResults,
    render_text,
    search,
)

__all__ = [
    "MatchContext",
    "SearchResult",
    "SearchResults",
    "render_text",
    "search",
]

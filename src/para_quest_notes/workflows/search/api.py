"""Library entry point for ``pqn-search``.

Agents and other workflows search the vault by calling :func:`search`
directly rather than shelling out to the CLI.
"""

from __future__ import annotations

from .builder import search
from .contract import MatchContext, SearchResult, SearchResults
from .render import render_text

__all__ = [
    "MatchContext",
    "SearchResult",
    "SearchResults",
    "render_text",
    "search",
]

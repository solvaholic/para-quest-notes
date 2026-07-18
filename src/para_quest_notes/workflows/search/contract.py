"""Public JSON contract for ``pqn-search`` results.

Stable across releases - agents and humans both consume this. Add fields
rather than rename.

The result set is a **flat list**, most-relevant first. Each result carries
its own ``supports`` list (the Quest(s) it serves) and a ``match_context``
saying where the hit landed (title vs body) with a short snippet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class MatchContext:
    """Where a keyword hit landed, plus a short snippet for context.

    ``where`` is ``"title"`` when at least one keyword matched the note's
    basename (title scope enabled), otherwise ``"body"``. ``snippet`` is the
    title itself for a title hit, or a whitespace-collapsed window around the
    first body match for a body hit.
    """

    where: str  # "title" | "body"
    snippet: str


@dataclass
class SearchResult:
    """One matching note.

    ``supports`` is the note's declared ``supports:`` list (normalized
    basenames) - the Quest(s) it serves. Deliberately not called ``quest``:
    ``quest:`` is the main/side/none classifier, ``supports:`` is which
    Quest(s) the note serves.
    """

    path: str  # vault-relative POSIX
    type: str | None  # "project" | "area" | "resource" | None
    supports: list[str] = field(default_factory=list)
    match_context: MatchContext = field(
        default_factory=lambda: MatchContext(where="body", snippet="")
    )
    # Internal ranking signal, surfaced for transparency. For non-Resources
    # this is 0 (backlink count only factors into Resource ranking).
    incoming_links: int = 0


@dataclass
class SearchResults:
    """Top-level result the CLI emits."""

    vault: str
    query: list[str] = field(default_factory=list)
    scope: dict[str, Any] = field(default_factory=dict)
    results: list[SearchResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": self.vault,
            "query": list(self.query),
            "scope": dict(self.scope),
            "summary": {"results": len(self.results)},
            "results": [
                {
                    "path": r.path,
                    "type": r.type,
                    "supports": list(r.supports),
                    "match_context": asdict(r.match_context),
                    "incoming_links": r.incoming_links,
                }
                for r in self.results
            ],
        }

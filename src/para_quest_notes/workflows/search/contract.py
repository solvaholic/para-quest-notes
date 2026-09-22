"""Public JSON contract for ``pqn-search`` results.

Stable across releases - agents and humans both consume this. Add fields
rather than rename.

The result set is a **flat list**, most-relevant first. Each result carries
its own ``supports`` list (the Quest(s) it serves) and a ``match_context``
saying where the hit landed (title vs body) with a short snippet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, TypeAlias

MatchLocation: TypeAlias = Literal["title", "body"]
LinkRelation: TypeAlias = Literal["mutual", "outgoing", "incoming"]
UnresolvedLinkReason: TypeAlias = Literal["missing", "ambiguous"]
ScopeValue: TypeAlias = bool | int | list[str] | str | None


@dataclass(frozen=True)
class MatchEvidence:
    """The preferred evidence for one distinct query keyword."""

    keyword: str
    where: MatchLocation
    snippet: str


@dataclass(frozen=True)
class MatchContext:
    """Where a keyword hit landed, plus a short snippet for context.

    ``where`` is ``"title"`` when at least one keyword matched the note's
    basename (title scope enabled), otherwise ``"body"``. ``snippet`` is the
    title itself for a title hit, or a whitespace-collapsed window around the
    first body match for a body hit.
    """

    where: MatchLocation
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
    # Ordered, one-item-per-distinct-keyword match evidence. Added after the
    # existing fields to preserve positional construction compatibility.
    matches: list[MatchEvidence] = field(default_factory=list)


@dataclass
class SearchResults:
    """Top-level result the CLI emits."""

    vault: str
    query: list[str] = field(default_factory=list)
    scope: dict[str, ScopeValue] = field(default_factory=dict)
    results: list[SearchResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
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
                    "matches": [asdict(match) for match in r.matches],
                }
                for r in self.results
            ],
        }


@dataclass(frozen=True)
class LinkContext:
    """How the requested target and one neighboring note are connected."""

    relation: LinkRelation
    outgoing_occurrences: int
    incoming_occurrences: int


@dataclass(frozen=True)
class ResolvedLinkTarget:
    """The uniquely resolved note at the center of a link lookup."""

    path: str
    type: str | None
    supports: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LinkSearchResult:
    """One direct outgoing link or incoming backlink."""

    path: str
    type: str | None
    supports: list[str] = field(default_factory=list)
    link_context: LinkContext = field(
        default_factory=lambda: LinkContext(
            relation="incoming",
            outgoing_occurrences=0,
            incoming_occurrences=0,
        )
    )


@dataclass(frozen=True)
class UnresolvedLink:
    """One unresolved outgoing link written in the requested target."""

    target: str
    occurrences: int
    reason: UnresolvedLinkReason
    candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class LinkSearchResults:
    """Top-level result for direct link traversal."""

    vault: str
    target: ResolvedLinkTarget
    scope: dict[str, ScopeValue] = field(default_factory=dict)
    results: list[LinkSearchResult] = field(default_factory=list)
    unresolved_links: list[UnresolvedLink] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        relation_counts = {
            relation: sum(result.link_context.relation == relation for result in self.results)
            for relation in ("outgoing", "incoming", "mutual")
        }
        return {
            "vault": self.vault,
            "mode": "links",
            "target": asdict(self.target),
            "scope": dict(self.scope),
            "summary": {
                "results": len(self.results),
                **relation_counts,
                "unresolved_outgoing": len(self.unresolved_links),
            },
            "results": [asdict(result) for result in self.results],
            "unresolved_links": [unresolved.to_dict() for unresolved in self.unresolved_links],
        }

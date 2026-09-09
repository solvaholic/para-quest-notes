"""Keyword search over the vault, PARA + Quest-aware.

Read-only, no LLM. Walks the vault, matches notes by title (basename) and/or
body keywords, filters by the ``--type`` / ``--quest`` scope, and ranks the
hits. The sibling of ``pqn-quests`` (#82): both consume ``vault/links.py`` and
``vault/scope.py``.

Why this earns its place over plain ``rg``: it is **PARA + Quest-aware**. It
filters by note type and Quest, and ranks Resources by how many active notes
link to them - an inbound wikilink is re-use, and re-use is evidence of value
(``docs/notes-system.md``: Resources are discovered via incoming wikilinks).

Ranking (v1), in order:

1. **Title hits before body hits.** A keyword in the basename beats one in the
   body.
2. **For Resources, tie-break by incoming-link count (desc).** Count links from
   active (non-archive) notes, *including* daily notes - daily-note links are
   signal. ``archive/`` links never count.
3. **Stable tie-break by vault-relative path.**

Scope: ``inbox/`` and daily notes are searched by default (that's where recent,
findable notes live); ``archive/`` is excluded unless ``include_archive`` is
set. The backlink index that powers ranking is always built from non-archive
notes, so archived notes can appear as results but never confer link weight.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from para_quest_notes.vault.frontmatter import split_note
from para_quest_notes.vault.links import build_backlink_index
from para_quest_notes.vault.scope import Scope, note_supports, para_type_of
from para_quest_notes.workflows.validate.pipeline import list_markdown_files

from .contract import MatchContext, MatchEvidence, MatchLocation, SearchResult, SearchResults

DEFAULT_SNIPPET_RADIUS = 40


@dataclass(frozen=True)
class _Keyword:
    """One distinct user-supplied keyword, retaining its first spelling."""

    original: str
    normalized: str


@dataclass(frozen=True)
class _KeywordHit:
    """The preferred enabled-field hit for one keyword.

    ``position`` stays internal. It lets the compatibility ``match_context``
    retain its existing earliest-body-match snippet without exposing offsets
    in the public JSON contract.
    """

    keyword: _Keyword
    where: MatchLocation
    position: int


def _distinct_keywords(query: list[str]) -> list[_Keyword]:
    """Return non-empty query keywords once, case-insensitively, in order."""
    seen: set[str] = set()
    keywords: list[_Keyword] = []
    for original in query:
        normalized = original.lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(_Keyword(original=original, normalized=normalized))
    return keywords


def _snippet_at(body: str, position: int, radius: int) -> str:
    """A whitespace-collapsed window around a body match at ``position``.

    ``radius`` characters on each side of the match. A ``radius`` of 0 means
    "no snippet" and returns the empty string.
    """
    if radius <= 0:
        return ""
    start = max(0, position - radius)
    end = min(len(body), position + radius)
    fragment = " ".join(body[start:end].split())
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(body) else ""
    return f"{prefix}{fragment}{suffix}"


def _keyword_hits(
    keywords: list[_Keyword],
    *,
    title: str,
    body: str,
    search_title: bool,
    search_content: bool,
) -> list[_KeywordHit]:
    """Locate every keyword's title-preferred evidence in enabled fields."""
    title_low = title.lower()
    body_low = body.lower()
    hits: list[_KeywordHit] = []
    for keyword in keywords:
        title_position = title_low.find(keyword.normalized) if search_title else -1
        if title_position >= 0:
            hits.append(_KeywordHit(keyword=keyword, where="title", position=title_position))
            continue

        body_position = body_low.find(keyword.normalized) if search_content else -1
        if body_position >= 0:
            hits.append(_KeywordHit(keyword=keyword, where="body", position=body_position))
    return hits


def _match_evidence(
    hits: list[_KeywordHit], *, title: str, body: str, radius: int
) -> list[MatchEvidence]:
    """Build the ordered public evidence list from keyword hits."""
    return [
        MatchEvidence(
            keyword=hit.keyword.original,
            where=hit.where,
            snippet=title
            if hit.where == "title" and radius > 0
            else (_snippet_at(body, hit.position, radius) if hit.where == "body" else ""),
        )
        for hit in hits
    ]


def _compatibility_context(
    hits: list[_KeywordHit], *, title: str, body: str, radius: int
) -> MatchContext:
    """Derive the legacy context from the richer, title-preferred evidence."""
    title_hit = next((hit for hit in hits if hit.where == "title"), None)
    if title_hit is not None:
        return MatchContext(where="title", snippet=title if radius > 0 else "")

    first_body_hit = min(hits, key=lambda hit: hit.position)
    return MatchContext(
        where="body",
        snippet=_snippet_at(body, first_body_hit.position, radius),
    )


def search(
    vault: Path,
    query: list[str],
    *,
    title: bool = False,
    content: bool = False,
    types: list[str] | None = None,
    quest: str | None = None,
    include_archive: bool = False,
    limit: int | None = None,
    snippet_radius: int = DEFAULT_SNIPPET_RADIUS,
) -> SearchResults:
    """Search ``vault`` for notes matching every keyword in ``query``.

    ``title`` / ``content`` select the fields to search; when **both are
    False** the search covers both (the default). Matching is case-insensitive
    substring, AND across keywords: a note is a result only when every keyword
    appears in the union of the enabled fields.

    ``types`` is an include-only PARA-type allow-list (``--type``); ``quest``
    restricts to notes whose ``supports:`` includes that Quest (``--quest``);
    ``include_archive`` pulls ``archive/`` into the search set; ``limit`` caps
    the number of results (``None`` = unlimited).

    ``snippet_radius`` is how many characters of context to show on each side
    of a body match (and it gates the title snippet); ``0`` suppresses
    snippets entirely. Negative values are clamped to ``0``.
    """
    radius = max(0, snippet_radius)
    search_title = title or not (title or content)
    search_content = content or not (title or content)
    keywords = _distinct_keywords(query)

    scope = Scope.from_args(types=types, quest=quest)

    # Ranking counts inbound links from active (non-archive) notes only, so
    # build the backlink index from the non-archive set regardless of the
    # search set. archive/ links never confer weight.
    active_files = list_markdown_files(vault, include_archive=False)
    backlinks = build_backlink_index(active_files)

    search_files = (
        active_files if not include_archive else list_markdown_files(vault, include_archive=True)
    )

    results: list[SearchResult] = []
    for md in search_files:
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        split = split_note(text)
        meta: dict[str, object] = {**split.backmatter, **split.frontmatter}

        title_text = md.stem
        body_text = split.body
        # A note is a result only when every keyword is satisfied by some
        # enabled field (AND across keywords, OR across fields).
        hits = _keyword_hits(
            keywords,
            title=title_text,
            body=body_text,
            search_title=search_title,
            search_content=search_content,
        )
        if not keywords or len(hits) != len(keywords):
            continue

        para_type = para_type_of(vault, md, meta)
        supports = note_supports(meta)
        if not scope.matches(para_type=para_type, supports=supports):
            continue

        incoming = len(backlinks.sources_for(md.stem)) if para_type == "resource" else 0

        results.append(
            SearchResult(
                path=md.relative_to(vault).as_posix(),
                type=para_type,
                supports=supports,
                match_context=_compatibility_context(
                    hits, title=title_text, body=body_text, radius=radius
                ),
                incoming_links=incoming,
                matches=_match_evidence(hits, title=title_text, body=body_text, radius=radius),
            )
        )

    # Rank: title hits first; then (Resources only) more inbound links first;
    # then a stable path tie-break.
    results.sort(
        key=lambda r: (
            0 if r.match_context.where == "title" else 1,
            -r.incoming_links,
            r.path,
        )
    )

    if limit is not None:
        results = results[:limit]

    return SearchResults(
        vault=str(vault),
        query=list(query),
        scope={
            "title": search_title,
            "content": search_content,
            "types": sorted(scope.types) if scope.types is not None else None,
            "quest": scope.quest,
            "include_archive": include_archive,
            "limit": limit,
            "snippet_radius": radius,
        },
        results=results,
    )

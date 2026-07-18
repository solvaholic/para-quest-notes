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

from pathlib import Path

from para_quest_notes.vault.frontmatter import split_note
from para_quest_notes.vault.links import build_backlink_index
from para_quest_notes.vault.scope import Scope, note_supports, para_type_of
from para_quest_notes.workflows.validate.pipeline import list_markdown_files

from .contract import MatchContext, SearchResult, SearchResults

DEFAULT_SNIPPET_RADIUS = 40


def _snippet(body: str, keywords_lower: list[str], radius: int) -> str:
    """A whitespace-collapsed window around the first body keyword match.

    ``radius`` characters on each side of the match. A ``radius`` of 0 means
    "no snippet" and returns the empty string. Falls back to the leading body
    text if no keyword is found (shouldn't happen for a body hit, but keeps
    the function total).
    """
    if radius <= 0:
        return ""
    low = body.lower()
    positions = [low.find(k) for k in keywords_lower if k in low]
    if not positions:
        return " ".join(body.split())[: 2 * radius].strip()
    pos = min(positions)
    start = max(0, pos - radius)
    end = min(len(body), pos + radius)
    fragment = " ".join(body[start:end].split())
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(body) else ""
    return f"{prefix}{fragment}{suffix}"


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
    keywords = [k.lower() for k in query if k]

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
        title_low = title_text.lower()
        body_low = body_text.lower()

        # A note is a result only when every keyword is satisfied by some
        # enabled field (AND across keywords, OR across fields).
        matched = keywords and all(
            (search_title and kw in title_low) or (search_content and kw in body_low)
            for kw in keywords
        )
        if not matched:
            continue

        para_type = para_type_of(vault, md, meta)
        supports = note_supports(meta)
        if not scope.matches(para_type=para_type, supports=supports):
            continue

        title_has_any = search_title and any(kw in title_low for kw in keywords)
        if title_has_any:
            snippet = title_text if radius > 0 else ""
            match = MatchContext(where="title", snippet=snippet)
        else:
            match = MatchContext(where="body", snippet=_snippet(body_text, keywords, radius))

        incoming = len(backlinks.sources_for(md.stem)) if para_type == "resource" else 0

        results.append(
            SearchResult(
                path=md.relative_to(vault).as_posix(),
                type=para_type,
                supports=supports,
                match_context=match,
                incoming_links=incoming,
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

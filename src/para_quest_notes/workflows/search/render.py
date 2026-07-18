"""Render :class:`SearchResults` as human-readable text.

A **flat list**, most-relevant first - mirroring the JSON. One bullet per
result carrying the vault-relative path, PARA type (with the inbound-link
count for Resources, since that count drives their ranking), any declared
``supports:``, and the match location plus snippet.
"""

from __future__ import annotations

from .contract import SearchResult, SearchResults


def _meta(result: SearchResult) -> str:
    """The parenthetical after the path: type, link count, supports."""
    parts: list[str] = [result.type or "untyped"]
    if result.type == "resource" and result.incoming_links:
        links = "link" if result.incoming_links == 1 else "links"
        parts.append(f"{result.incoming_links} {links}")
    if result.supports:
        parts.append(f"supports: {', '.join(result.supports)}")
    return ", ".join(parts)


def _bullet(result: SearchResult) -> str:
    where = result.match_context.where
    snippet = result.match_context.snippet
    return f'- {result.path} ({_meta(result)}) - {where}: "{snippet}"'


def render_text(results: SearchResults) -> str:
    """Render the results. Always ends with a single trailing newline."""
    query = " ".join(results.query)
    n = len(results.results)
    header = f'# Search results for "{query}" ({n} match{"" if n == 1 else "es"})'

    if not results.results:
        return f"{header}\n\nNo matches.\n"

    lines = [header, ""]
    lines.extend(_bullet(r) for r in results.results)
    return "\n".join(lines) + "\n"

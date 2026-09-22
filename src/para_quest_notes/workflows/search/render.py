"""Render :class:`SearchResults` as human-readable text.

A **flat list**, most-relevant first - mirroring the JSON. One bullet per
result carrying the vault-relative path, PARA type (with the inbound-link
count for Resources, since that count drives their ranking), any declared
``supports:``, and the match location plus snippet.
"""

from __future__ import annotations

from .contract import LinkSearchResult, LinkSearchResults, SearchResult, SearchResults


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
    if len(result.matches) > 1:
        evidence = "; ".join(
            f"{match.keyword} ({match.where})" + (f': "{match.snippet}"' if match.snippet else "")
            for match in result.matches
        )
        return f"- {result.path} ({_meta(result)}) - matches: {evidence}"

    where = result.match_context.where
    snippet = result.match_context.snippet
    tail = f' - {where}: "{snippet}"' if snippet else f" - {where}"
    return f"- {result.path} ({_meta(result)}){tail}"


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


def _link_meta(result: LinkSearchResult) -> str:
    parts = [result.type or "untyped"]
    if result.supports:
        parts.append(f"supports: {', '.join(result.supports)}")
    return ", ".join(parts)


def _link_bullet(result: LinkSearchResult) -> str:
    context = result.link_context
    return (
        f"- {result.path} ({_link_meta(result)}) - {context.relation}: "
        f"outgoing {context.outgoing_occurrences}, "
        f"incoming {context.incoming_occurrences}"
    )


def render_link_text(results: LinkSearchResults) -> str:
    """Render direct link neighbors and unresolved outgoing targets."""
    count = len(results.results)
    lines = [
        f'# Link neighbors for "{results.target.path}" ({count} match{"" if count == 1 else "es"})',
        "",
    ]
    if results.results:
        lines.extend(_link_bullet(result) for result in results.results)
    else:
        lines.append("No linked notes.")

    if results.unresolved_links:
        lines.extend(["", "## Unresolved outgoing links", ""])
        for unresolved in results.unresolved_links:
            occurrence_label = "occurrence" if unresolved.occurrences == 1 else "occurrences"
            candidate_text = (
                f" - candidates: {', '.join(unresolved.candidates)}"
                if unresolved.candidates
                else ""
            )
            lines.append(
                f"- {unresolved.target} ({unresolved.reason}, "
                f"{unresolved.occurrences} {occurrence_label}){candidate_text}"
            )

    return "\n".join(lines) + "\n"

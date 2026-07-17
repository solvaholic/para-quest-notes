"""Vault wikilink parsing and backlink index.

The first of the link-aware building blocks. Lifted out of
``ingest_inbox/steps/apply_move.py`` (``_WIKILINK`` / ``_scan_wikilinks``)
so every link-aware CLI shares one wikilink parser and one backlink scan:

* ``pqn-quests`` (#86) surfaces Resources via incoming Area/Project links.
* ``pqn-search`` (#82) ranks Resources by incoming-link count.

Wikilinks resolve by **basename**, case-insensitively — matching Obsidian's
resolver and most single-user vault filesystems. ``[[Foo]]``,
``[[Foo#heading]]``, and ``[[Foo|alias]]`` all target the note ``Foo``.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Capture group 1 is the link target (the note basename). Anchors (``#...``)
# and aliases (``|...``) are captured separately so callers can rewrite links
# without losing them.
WIKILINK = re.compile(r"\[\[([^\[\]|#]+?)(#[^\[\]|]+?)?(\|[^\[\]]+?)?\]\]")


def _normalize(stem: str) -> str:
    """Normalize a link target for case-insensitive basename matching."""
    return stem.strip().lower()


def iter_markdown(vault: Path, *, include_archive: bool = False) -> list[Path]:
    """Return ``*.md`` files under ``vault``, excluding ``archive/`` by default.

    Deliberately minimal (archive-only exclusion) to preserve the historical
    behavior of ``apply_move``'s wikilink scan. Callers that need richer
    exclusions (``.git``, ``inbox/`` …) build their own file list and hand it
    to :func:`build_backlink_index`.
    """
    out: list[Path] = []
    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault).parts
        if not include_archive and rel and rel[0] == "archive":
            continue
        out.append(p)
    return out


def link_targets(text: str) -> list[str]:
    """Return every wikilink target basename in ``text`` (order preserved)."""
    return [m.group(1).strip() for m in WIKILINK.finditer(text)]


def scan_backlinks(
    vault: Path,
    target_stem: str,
    *,
    exclude: Path | None = None,
    include_archive: bool = False,
) -> list[dict[str, Any]]:
    """Report notes that link to ``target_stem``, with occurrence counts.

    Returns ``[{"file": <vault-relative posix>, "occurrences": <int>}]`` for
    each note containing at least one wikilink to ``target_stem`` (matched by
    basename, case-insensitively). ``exclude`` skips one note (e.g. the note
    being renamed). This is the shape ``apply_move`` reports in dry-run.
    """
    target = _normalize(target_stem)
    exclude_resolved = exclude.resolve() if exclude is not None else None
    hits: list[dict[str, Any]] = []
    for md in iter_markdown(vault, include_archive=include_archive):
        if exclude_resolved is not None and md.resolve() == exclude_resolved:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        count = sum(1 for m in WIKILINK.finditer(text) if _normalize(m.group(1)) == target)
        if count:
            hits.append({"file": md.relative_to(vault).as_posix(), "occurrences": count})
    return hits


@dataclass(frozen=True)
class Backlink:
    """One note linking to a target, with how many times it does so."""

    source: Path
    occurrences: int


@dataclass
class BacklinkIndex:
    """Which notes link to a given note, keyed by normalized basename.

    Built once from a file list, then queried repeatedly. Cheaper than
    re-scanning the vault per target, which matters for a whole-vault index.
    """

    _by_target: dict[str, list[Backlink]] = field(default_factory=dict)

    def sources_for(self, target_stem: str) -> list[Backlink]:
        """Return the backlinks pointing at ``target_stem`` (basename match)."""
        return self._by_target.get(_normalize(target_stem), [])


def build_backlink_index(files: Iterable[Path]) -> BacklinkIndex:
    """Build a :class:`BacklinkIndex` from an explicit set of note paths.

    The caller controls the file set (and thus which notes count as link
    *sources*) — pass only active notes to exclude ``archive/``, drop
    ``inbox/``, and so on. Targets are keyed by normalized basename, so a
    link resolves to any note sharing that basename (validate flags the
    ambiguity separately).
    """
    index = BacklinkIndex()
    for md in files:
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        counts: Counter[str] = Counter(_normalize(t) for t in link_targets(text))
        for target, occurrences in counts.items():
            index._by_target.setdefault(target, []).append(
                Backlink(source=md, occurrences=occurrences)
            )
    return index

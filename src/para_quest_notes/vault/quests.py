"""Discover Main + Side Quests declared in the vault.

The Quest list comes from notes under ``<vault>/areas/`` whose
frontmatter declares ``quest-kind: main`` or ``quest-kind: side`` (the
legacy ``quest:`` spelling is tolerated on read with a warning). See
``docs/notes-system.md``.

Also provides :func:`resolve_quest_from_path`, a deterministic (no-LLM)
helper that infers a declared Quest from a destination path by checking
same-named Area notes and sibling consensus. See issue #47.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from para_quest_notes.vault.frontmatter import (
    read_quest_kind,
    split_note,
    warn_legacy_quest_key,
)


@dataclass(frozen=True)
class Quest:
    name: str  # title-stem of the note, e.g. "Health"
    quest_kind: str  # "main" or "side"
    supports: tuple[str, ...] = ()  # raw wikilink stems, e.g. ("Health",)
    path: Path | None = None


def _strip_wikilink(s: str) -> str:
    s = s.strip()
    if s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    # Drop alias.
    if "|" in s:
        s = s.split("|", 1)[0]
    return s.strip()


def discover_quests(vault: Path) -> list[Quest]:
    """Return Quests declared under ``<vault>/areas/*.md``.

    Returns Main Quests first, then Side Quests, each group sorted by
    name. Frontmatter is the canonical location; legacy notes that
    declare ``quest-kind:`` (or the legacy ``quest:`` spelling) in
    trailing backmatter are still discovered (backmatter is tolerated on
    read, migrated on touch — see ``docs/PLAN.md`` "Open questions —
    decided 2026-05-12"). Frontmatter wins when both are present.
    """
    areas_dir = vault / "areas"
    if not areas_dir.is_dir():
        return []

    main: list[Quest] = []
    side: list[Quest] = []
    for md in sorted(areas_dir.rglob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        split = split_note(text)
        meta: dict[str, object] = {**split.backmatter, **split.frontmatter}
        kind, used_legacy = read_quest_kind(meta)
        if used_legacy:
            warn_legacy_quest_key(md)
        if kind not in ("main", "side"):
            continue
        supports_raw = meta.get("supports") or []
        if not isinstance(supports_raw, list):
            supports_raw = [supports_raw]
        supports = tuple(_strip_wikilink(str(s)) for s in supports_raw if s)
        q = Quest(
            name=md.stem,
            quest_kind=str(kind),
            supports=supports,
            path=md,
        )
        (main if kind == "main" else side).append(q)

    main.sort(key=lambda q: q.name)
    side.sort(key=lambda q: q.name)
    return [*main, *side]


# ---------------------------------------------------------------------------
# Deterministic Quest inference from destination path (#47)
# ---------------------------------------------------------------------------

_WORD_SPLIT_RE = re.compile(r"[\s_\-]+")


def _to_snake_case(name: str) -> str:
    """Normalize a name to snake_case for matching against area note stems."""
    # Strip .md suffix if present
    if name.lower().endswith(".md"):
        name = name[:-3]
    # Split on whitespace, underscores, hyphens
    parts = _WORD_SPLIT_RE.split(name.strip())
    return "_".join(p.lower() for p in parts if p)


def _read_quest_from_note(path: Path) -> list[str]:
    """Read the declared quest supports from a note's frontmatter/backmatter.

    Returns the list of Quest names this note supports (from the
    ``supports:`` field, stripped of wikilink syntax). Returns an empty
    list if the note has no ``supports:`` or doesn't declare a quest.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    split = split_note(text)
    meta: dict[str, object] = {**split.backmatter, **split.frontmatter}
    quest_kind, used_legacy = read_quest_kind(meta)
    if used_legacy:
        warn_legacy_quest_key(path)
    if quest_kind not in ("main", "side"):
        return []
    supports_raw = meta.get("supports") or []
    if not isinstance(supports_raw, list):
        supports_raw = [supports_raw]
    return [_strip_wikilink(str(s)) for s in supports_raw if s]


def _find_area_note(vault: Path, match_key: str) -> Path | None:
    """Find an area note whose snake_case stem matches ``match_key``.

    Searches ``<vault>/areas/`` recursively. Returns the first match
    (there should be at most one per the uniqueness invariant).
    """
    areas_dir = vault / "areas"
    if not areas_dir.is_dir():
        return None
    target = _to_snake_case(match_key)
    if not target:
        return None
    for md in sorted(areas_dir.rglob("*.md")):
        if _to_snake_case(md.stem) == target:
            return md
    return None


def _sibling_consensus(vault: Path, dest_dir: str, valid_quests: set[str]) -> list[str]:
    """Check sibling notes in the destination directory for Quest consensus.

    Returns the Quest names that appear most frequently among siblings'
    ``supports:`` declarations. Only returns a result when there's a
    clear majority (one quest supported by > half of declaring siblings).
    """
    dir_path = vault / dest_dir
    if not dir_path.is_dir():
        return []
    quest_counts: Counter[str] = Counter()
    declaring_siblings = 0
    for md in sorted(dir_path.glob("*.md")):
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        split = split_note(text)
        meta: dict[str, object] = {**split.backmatter, **split.frontmatter}
        supports_raw = meta.get("supports") or []
        if not isinstance(supports_raw, list):
            supports_raw = [supports_raw]
        quests_here = [_strip_wikilink(str(s)) for s in supports_raw if s]
        # Only count notes that actually declare quest support
        valid_here = [q for q in quests_here if q in valid_quests]
        if valid_here:
            declaring_siblings += 1
            for q in valid_here:
                quest_counts[q] += 1

    if not quest_counts or declaring_siblings == 0:
        return []

    # Require a clear majority: top quest supported by > half of declaring siblings
    top_quest, top_count = quest_counts.most_common(1)[0]
    if top_count > declaring_siblings / 2:
        return [top_quest]
    return []


@dataclass(frozen=True)
class ResolvedQuest:
    """Result of deterministic Quest resolution."""

    quests: list[str]
    source: str  # "area_note" | "sibling_consensus" | "miss"


def resolve_quest_from_path(
    vault: Path,
    dest_path: str,
    *,
    valid_quests: set[str] | None = None,
) -> ResolvedQuest:
    """Deterministic (no-LLM) Quest inference from a destination path.

    Checks, in order:

    1. **Same-named Area note (filename)** - if ``areas/<stem>.md``
       exists (where stem is the filename stem, snake_case normalized)
       and declares ``supports:``, those Quests win outright.
    2. **Same-named Area note (path segments)** - walk up the path's
       intermediate directories (most-specific first), checking each
       against area notes. First match wins.
    3. **Sibling consensus** - other notes already in the destination
       folder that declare a Quest. Used only when no same-named Area
       note exists.

    ``dest_path`` is a vault-relative posix path like
    ``projects/sub/filename.md`` or just a bare basename like
    ``my note.md``.

    ``valid_quests`` is the set of known Quest names in the vault. When
    provided, sibling consensus only counts Quests in this set.

    Returns a :class:`ResolvedQuest` with the inferred quests and the
    source of the inference. On miss, ``quests`` is empty and ``source``
    is ``"miss"``.
    """
    from pathlib import PurePosixPath

    parts = PurePosixPath(dest_path)
    stem = parts.stem  # e.g. "my note" from "projects/my note.md"

    # Step 1: Same-named Area note (filename stem)
    area_note = _find_area_note(vault, stem)
    if area_note is not None:
        quests = _read_quest_from_note(area_note)
        if quests:
            if valid_quests is not None:
                quests = [q for q in quests if q in valid_quests]
            if quests:
                return ResolvedQuest(quests=quests, source="area_note")

    # Step 2: Same-named Area note (path segments, most-specific first)
    # For "projects/health/running/Note.md", try "running" then "health"
    # Skip the PARA top-dir (first segment like "projects")
    all_parts = list(parts.parts)
    # Remove filename (last) and PARA dir (first, if present)
    dir_segments = all_parts[1:-1] if len(all_parts) > 2 else []
    for segment in reversed(dir_segments):
        area_note = _find_area_note(vault, segment)
        if area_note is not None:
            quests = _read_quest_from_note(area_note)
            if quests:
                if valid_quests is not None:
                    quests = [q for q in quests if q in valid_quests]
                if quests:
                    return ResolvedQuest(quests=quests, source="area_note")

    # Step 3: Sibling consensus
    dest_dir = str(parts.parent) if str(parts.parent) != "." else ""
    if dest_dir and valid_quests:
        consensus = _sibling_consensus(vault, dest_dir, valid_quests)
        if consensus:
            return ResolvedQuest(quests=consensus, source="sibling_consensus")

    # Miss: fall through
    return ResolvedQuest(quests=[], source="miss")

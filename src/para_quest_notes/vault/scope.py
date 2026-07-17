"""PARA-type detection and the ``--type`` / ``--quest`` scope filter.

The second shared building block for link-aware CLIs. ``pqn-quests`` (#86)
lands it; ``pqn-search`` (#82) inherits identical scoping semantics.

Two orthogonal axes:

* **PARA type** — ``project`` | ``area`` | ``resource``. Read from
  frontmatter ``type:`` (canonical); fall back to the note's top-level
  directory when frontmatter is silent.
* **Quest association** — a note's ``supports:`` list (wikilinks to the
  Quest notes it serves). Distinct from ``quest:`` (the main/side/none
  classifier of the note itself).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PARA_TYPES: tuple[str, ...] = ("project", "area", "resource")

# Top-level PARA directory -> canonical type.
_DIR_TO_TYPE: dict[str, str] = {
    "projects": "project",
    "areas": "area",
    "resources": "resource",
}


def strip_wikilink(s: str) -> str:
    """Return the target basename of a wikilink string.

    ``"[[Health|My health]]"`` -> ``"Health"``. Plain strings pass through
    with surrounding whitespace trimmed.
    """
    s = s.strip()
    if s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    if "|" in s:  # drop the alias
        s = s.split("|", 1)[0]
    return s.strip()


def note_supports(meta: dict[str, Any]) -> list[str]:
    """Return the Quest names a note declares in ``supports:`` (wikilinks stripped).

    Tolerates a scalar ``supports:`` (wrapped to a one-item list) and drops
    empty entries. ``meta`` is the merged frontmatter/backmatter mapping.
    """
    raw = meta.get("supports") or []
    if not isinstance(raw, list):
        raw = [raw]
    return [strip_wikilink(str(s)) for s in raw if s]


def para_type_of(vault: Path, path: Path, meta: dict[str, Any]) -> str | None:
    """Infer a note's PARA type: ``project`` | ``area`` | ``resource`` | ``None``.

    Frontmatter ``type:`` wins when it names a known PARA type. Otherwise we
    fall back to the note's top-level directory (``areas/``, ``projects/``,
    ``resources/``). Under ``archive/`` — a *location*, not a type — we look at
    the segment after ``archive/``. Returns ``None`` when neither source
    resolves (e.g. a note in a free-form top-level folder with no ``type:``).
    """
    declared = meta.get("type")
    if isinstance(declared, str) and declared.lower() in PARA_TYPES:
        return declared.lower()

    rel = path.relative_to(vault).parts
    if not rel:
        return None
    top = rel[0]
    if top == "archive" and len(rel) > 1:
        top = rel[1]
    return _DIR_TO_TYPE.get(top)


@dataclass(frozen=True)
class Scope:
    """A ``--type`` / ``--quest`` filter over notes.

    ``types`` is an include-only allow-list (``None`` = every PARA type,
    matching the ``--type``-omitted default). ``quest`` restricts to notes
    whose ``supports:`` includes that Quest (normalized basename); ``None``
    keeps every Quest.
    """

    types: frozenset[str] | None = None
    quest: str | None = None

    @classmethod
    def from_args(
        cls,
        *,
        types: Sequence[str] | None = None,
        quest: str | None = None,
    ) -> Scope:
        """Build a :class:`Scope` from raw CLI values.

        ``types`` empty or ``None`` means "all types". ``quest`` is stripped
        of wikilink syntax and lower-cased for matching.
        """
        type_set = frozenset(t.lower() for t in types) if types else None
        quest_norm = strip_wikilink(quest).lower() if quest else None
        return cls(types=type_set, quest=quest_norm or None)

    def allows_type(self, para_type: str | None) -> bool:
        """True when ``para_type`` passes the ``--type`` allow-list."""
        if self.types is None:
            return True
        return para_type in self.types

    def matches_quest(self, supports: Sequence[str]) -> bool:
        """True when ``supports`` satisfies the ``--quest`` filter.

        Unfiltered (``quest is None``) always matches. Otherwise a note
        matches when any of its ``supports`` entries equals the target Quest
        (case-insensitive basename compare).
        """
        if self.quest is None:
            return True
        return any(strip_wikilink(s).lower() == self.quest for s in supports)

    def matches(self, *, para_type: str | None, supports: Sequence[str]) -> bool:
        """True when a note passes both the type and quest filters."""
        return self.allows_type(para_type) and self.matches_quest(supports)

"""Note shape axes — what the ingest workflow will reason over.

A generated note picks one value from each axis plus zero or more
:class:`Quirk` flags. The combinations span the spread the ingest
workflow encounters in the wild: clean spec-conforming notes through
to bare topic-organized text files with no frontmatter at all.

These names are deliberately neutral. The product does *not* refer to
historical "gen1/gen2/gen3" organization styles — that terminology is
specific to one author's note history and would be meaningless to a
new user.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum


class LocationKind(StrEnum):
    """Where in the vault tree a note lives."""

    PARA = "para"  # under projects/, areas/, or resources/
    TOPIC = "topic"  # arbitrary topic dir like Home/, Work/
    QUEST = "quest"  # quest-first dir like Health/, Maintain Home/
    INBOX = "inbox"  # inbox/
    DAILY = "daily"  # resources/daily_notes/YYYY/MM/


class FrontmatterKind(StrEnum):
    """What the YAML frontmatter looks like."""

    NONE = "none"  # no frontmatter at all
    OBSIDIAN_ONLY = "obsidian_only"  # tags/aliases, no PARA/Quest fields
    PARTIAL_PARA = "partial_para"  # has a PARA type field, but no quest/supports
    FULL = "full"  # spec-compliant type + quest + supports


class Quirk(StrEnum):
    """Orthogonal messiness flags. Zero or more per note."""

    AMBIGUOUS_QUEST = "ambiguous_quest"  # body mentions multiple Quests
    HAS_TASKS = "has_tasks"  # adds Obsidian task lines
    CLOSED_TASKS_ONLY = "closed_tasks_only"  # all tasks done -> archive-eligible
    HAS_ATTACHMENTS = "has_attachments"  # sibling files in same dir
    DUPLICATE_TITLE = "duplicate_title"  # collides with another corpus note title
    BROKEN_WIKILINK = "broken_wikilink"  # links to a non-existent note
    MISSING_SUPPORTS = "missing_supports"  # tasks present but no supports field


# Quirks that only make sense on certain frontmatter kinds. Used to
# avoid generating contradictions like MISSING_SUPPORTS on a note with
# no frontmatter at all.
_QUIRK_REQUIRES_FRONTMATTER: frozenset[Quirk] = frozenset({Quirk.MISSING_SUPPORTS})


@dataclass(frozen=True)
class Shape:
    location_kind: LocationKind
    frontmatter_kind: FrontmatterKind
    quirks: frozenset[Quirk] = field(default_factory=frozenset)

    def has(self, quirk: Quirk) -> bool:
        return quirk in self.quirks


# Distribution of frontmatter kinds for general (non-inbox, non-daily)
# notes. The spec target is FULL, but a real arriving vault has plenty
# of bare and partial notes.
_DEFAULT_FRONTMATTER_WEIGHTS: dict[FrontmatterKind, float] = {
    FrontmatterKind.NONE: 0.20,
    FrontmatterKind.OBSIDIAN_ONLY: 0.20,
    FrontmatterKind.PARTIAL_PARA: 0.20,
    FrontmatterKind.FULL: 0.40,
}


def _weighted_choice(rng: random.Random, weights: dict[FrontmatterKind, float]) -> FrontmatterKind:
    keys = list(weights.keys())
    values = [weights[k] for k in keys]
    return rng.choices(keys, weights=values, k=1)[0]


def sample_frontmatter(
    rng: random.Random,
    location_kind: LocationKind,
    *,
    weights: dict[FrontmatterKind, float] | None = None,
) -> FrontmatterKind:
    """Pick a frontmatter kind appropriate for the location.

    Inbox and daily notes lean bare — that matches reality, and the
    spec exempts them from the "must declare supports" rule.
    """
    if location_kind is LocationKind.INBOX:
        # Inbox is by definition messy; mostly bare or Obsidian-only.
        return rng.choices(
            [FrontmatterKind.NONE, FrontmatterKind.OBSIDIAN_ONLY, FrontmatterKind.PARTIAL_PARA],
            weights=[0.6, 0.3, 0.1],
            k=1,
        )[0]
    if location_kind is LocationKind.DAILY:
        # Daily notes inherit Quest context from contents; usually bare.
        return rng.choices(
            [FrontmatterKind.NONE, FrontmatterKind.OBSIDIAN_ONLY],
            weights=[0.7, 0.3],
            k=1,
        )[0]
    return _weighted_choice(rng, weights or _DEFAULT_FRONTMATTER_WEIGHTS)


def sample_quirks(
    rng: random.Random,
    frontmatter_kind: FrontmatterKind,
    *,
    quirk_rate: float,
    candidates: tuple[Quirk, ...] = tuple(Quirk),
) -> frozenset[Quirk]:
    """Independently flip each candidate quirk with probability ``quirk_rate``.

    Quirks that require frontmatter are skipped when the note has none.
    """
    chosen: set[Quirk] = set()
    for quirk in candidates:
        if quirk in _QUIRK_REQUIRES_FRONTMATTER and frontmatter_kind is FrontmatterKind.NONE:
            continue
        if rng.random() < quirk_rate:
            chosen.add(quirk)
    # CLOSED_TASKS_ONLY implies HAS_TASKS — if we picked one, force the other.
    if Quirk.CLOSED_TASKS_ONLY in chosen:
        chosen.add(Quirk.HAS_TASKS)
    return frozenset(chosen)


def sample_shape(
    rng: random.Random,
    location_kind: LocationKind,
    *,
    quirk_rate: float,
    frontmatter_weights: dict[FrontmatterKind, float] | None = None,
) -> Shape:
    """Build a complete :class:`Shape` for a note in ``location_kind``."""
    fm = sample_frontmatter(rng, location_kind, weights=frontmatter_weights)
    quirks = sample_quirks(rng, fm, quirk_rate=quirk_rate)
    return Shape(location_kind=location_kind, frontmatter_kind=fm, quirks=quirks)


__all__ = [
    "FrontmatterKind",
    "LocationKind",
    "Quirk",
    "Shape",
    "sample_frontmatter",
    "sample_quirks",
    "sample_shape",
]

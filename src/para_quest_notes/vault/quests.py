"""Discover Main + Side Quests declared in the vault.

The Quest list comes from notes under ``<vault>/areas/`` whose
frontmatter declares ``quest: main`` or ``quest: side``. See
``docs/notes-system.md``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from para_quest_notes.vault.frontmatter import parse


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
    name. Notes without recognizable frontmatter are skipped.
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
        parsed = parse(text)
        kind = parsed.frontmatter.get("quest")
        if kind not in ("main", "side"):
            continue
        supports_raw = parsed.frontmatter.get("supports") or []
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

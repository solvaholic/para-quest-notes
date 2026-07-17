"""Public JSON contract for ``pqn-quests`` results.

Stable across releases — agents and humans both consume this. Add fields
rather than rename.

The JSON is **flat**: every note appears exactly once, carrying its own
``supports`` list plus the ``quests`` it rolls up under. Consumers group by
``quests`` themselves; the grouped, possibly-duplicated view lives only in
the markdown renderer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class QuestRef:
    """One declared Quest, in index (section) order."""

    name: str  # note stem, e.g. "Health"
    quest_kind: str  # "main" or "side"


@dataclass
class NoteEntry:
    """One note in the index, appearing exactly once.

    ``supports`` is the note's own declared ``supports:`` list (normalized
    basenames). ``quests`` is where the note *rolls up* in the index: for
    Areas/Projects that's its supports intersected with declared Quests; for
    Resources it's the union of the Quests of the active Areas/Projects that
    link to it. ``capability`` notes and ``unassigned`` notes have an empty
    ``quests``.
    """

    path: str  # vault-relative POSIX
    title: str  # note stem
    type: str | None  # "project" | "area" | "resource" | None
    quest: str  # "main" | "side" | "none"
    supports: list[str] = field(default_factory=list)
    quests: list[str] = field(default_factory=list)
    capability: bool = False
    unassigned: bool = False
    archived: bool = False


@dataclass
class QuestIndex:
    """Top-level result the CLI emits."""

    vault: str
    scope: dict[str, Any] = field(default_factory=dict)
    quests: list[QuestRef] = field(default_factory=list)
    notes: list[NoteEntry] = field(default_factory=list)

    def notes_for_quest(self, quest_name: str) -> list[NoteEntry]:
        """Notes that roll up under ``quest_name`` (case-insensitive)."""
        key = quest_name.strip().lower()
        return [n for n in self.notes if any(q.lower() == key for q in n.quests)]

    @property
    def capabilities(self) -> list[NoteEntry]:
        return [n for n in self.notes if n.capability]

    @property
    def unassigned(self) -> list[NoteEntry]:
        return [n for n in self.notes if n.unassigned]

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": self.vault,
            "scope": dict(self.scope),
            "summary": {
                "quests": len(self.quests),
                "notes": len(self.notes),
                "capabilities": len(self.capabilities),
                "unassigned": len(self.unassigned),
            },
            "quests": [asdict(q) for q in self.quests],
            "notes": [asdict(n) for n in self.notes],
        }

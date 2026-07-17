"""Public JSON contract for ``pqn-tasks`` results.

Stable across releases — agents and humans both consume this. Add
fields rather than rename. Mirrors the flat shape of ``pqn-validate``:
one flat ``tasks`` list plus a ``summary``. Grouping (``--group-by``) is
a presentation concern applied by the CLI's text renderer, not encoded
into the JSON structure — consumers regroup on the per-task fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Bucket = Literal["overdue", "due_today", "upcoming"]

# Human-facing bucket order (most urgent first).
BUCKET_ORDER: tuple[Bucket, ...] = ("overdue", "due_today", "upcoming")

# Marker used when a task's note declares no supporting Quest/Area.
UNASSIGNED = "unassigned"


@dataclass
class TaskItem:
    """One reportable task: an open/in-progress task carrying a due date.

    ``path`` is vault-relative POSIX. ``line`` is 1-based into the file.
    ``description`` is the task text with trailing Tasks emoji-metadata
    and block id stripped for display; ``raw`` keeps the original text.
    ``areas`` / ``quests`` are the grouping keys derived from the note's
    ``supports:`` frontmatter (``quests`` rolls Side Quests up to their
    Main Quest). Either may be empty when the note declares no support.
    """

    path: str
    line: int
    description: str
    raw: str
    state: str
    bucket: Bucket
    due: str | None = None
    scheduled: str | None = None
    start: str | None = None
    block_id: str | None = None
    supports: list[str] = field(default_factory=list)
    areas: list[str] = field(default_factory=list)
    quests: list[str] = field(default_factory=list)


@dataclass
class TasksReport:
    """Top-level result the CLI emits."""

    vault: str
    reference_date: str
    due_in: int
    group_by: str
    include_archive: bool
    files_scanned: int = 0
    tasks: list[TaskItem] = field(default_factory=list)

    def _in(self, bucket: Bucket) -> list[TaskItem]:
        return [t for t in self.tasks if t.bucket == bucket]

    @property
    def overdue(self) -> list[TaskItem]:
        return self._in("overdue")

    @property
    def due_today(self) -> list[TaskItem]:
        return self._in("due_today")

    @property
    def upcoming(self) -> list[TaskItem]:
        return self._in("upcoming")

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": self.vault,
            "reference_date": self.reference_date,
            "due_in": self.due_in,
            "group_by": self.group_by,
            "include_archive": self.include_archive,
            "files_scanned": self.files_scanned,
            "summary": {
                "total": len(self.tasks),
                "overdue": len(self.overdue),
                "due_today": len(self.due_today),
                "upcoming": len(self.upcoming),
            },
            "tasks": [asdict(t) for t in self.tasks],
        }

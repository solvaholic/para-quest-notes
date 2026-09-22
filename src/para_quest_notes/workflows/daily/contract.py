"""Public JSON contract for ``pqn-daily`` results.

Stable across releases. Add fields rather than rename.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

TaskRoundupAction = Literal["insert", "replace", "unchanged"]


@dataclass
class DailyInputs:
    """User-supplied inputs for selecting one daily note."""

    target: str  # vault-relative path or bare basename (with or without .md)
    create_missing: bool = False
    task_roundup: bool = False


@dataclass
class DailyPlan:
    """What the workflow decided to do (populated even on dry-run)."""

    source: str | None = None  # vault-relative posix
    destination: str | None = None  # vault-relative posix
    date: str | None = None  # ISO YYYY-MM-DD
    h1_inserted: bool = False
    frontmatter_migrated: bool = False
    already_at_destination: bool = False
    would_create: bool = False


@dataclass
class TaskRoundupResult:
    """Summary of a requested managed task roundup."""

    action: TaskRoundupAction
    applied: bool
    reference_date: str
    due_in: int
    group_by: str
    date_fields: list[str]
    include_archive: bool
    unscheduled: str
    files_scanned: int
    summary: dict[str, int]


@dataclass
class DailyResult:
    """Result of one ``pqn-daily`` invocation."""

    vault: str
    apply: bool
    ok: bool = True
    plan: DailyPlan = field(default_factory=DailyPlan)
    moved: bool = False
    created: bool = False
    task_roundup: TaskRoundupResult | None = None
    opened: bool = False
    open_path: str | None = None
    open_error: str | None = None
    escalation: dict[str, Any] | None = None
    error: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": self.vault,
            "apply": self.apply,
            "ok": self.ok,
            "plan": asdict(self.plan),
            "moved": self.moved,
            "created": self.created,
            "task_roundup": (asdict(self.task_roundup) if self.task_roundup is not None else None),
            "opened": self.opened,
            "open_path": self.open_path,
            "open_error": self.open_error,
            "escalation": self.escalation,
            "error": self.error,
            "run_id": self.run_id,
        }

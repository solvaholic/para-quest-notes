"""Public JSON contract for ``pqn-archive`` results.

Stable across releases. Add fields rather than rename.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ArchiveInputs:
    """User-supplied inputs for archiving one Project."""

    target: str  # vault-relative path or bare basename (with or without .md)
    outcome: str | None = None
    cancel_open_tasks: bool = False


@dataclass
class ArchivePlan:
    """What the workflow decided to do (populated even on dry-run)."""

    source: str | None = None  # vault-relative posix
    destination: str | None = None  # vault-relative posix
    open_tasks: list[dict[str, Any]] = field(default_factory=list)
    tasks_cancelled: int = 0
    outcome_action: str = "none"  # "kept" | "inserted" | "none"
    frontmatter_migrated: bool = False


@dataclass
class ArchiveResult:
    """Result of one ``pqn-archive`` invocation."""

    vault: str
    apply: bool
    ok: bool = True
    plan: ArchivePlan = field(default_factory=ArchivePlan)
    moved: bool = False
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
            "escalation": self.escalation,
            "error": self.error,
            "run_id": self.run_id,
        }

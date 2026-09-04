"""Public JSON contract for ``pqn-daily`` results.

Stable across releases. Add fields rather than rename.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DailyInputs:
    """User-supplied inputs for selecting one daily note."""

    target: str  # vault-relative path or bare basename (with or without .md)
    create_missing: bool = False


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
class DailyResult:
    """Result of one ``pqn-daily`` invocation."""

    vault: str
    apply: bool
    ok: bool = True
    plan: DailyPlan = field(default_factory=DailyPlan)
    moved: bool = False
    created: bool = False
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
            "opened": self.opened,
            "open_path": self.open_path,
            "open_error": self.open_error,
            "escalation": self.escalation,
            "error": self.error,
            "run_id": self.run_id,
        }

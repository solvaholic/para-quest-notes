"""Public JSON contract for ``pqn-daily`` results.

Stable across releases. Add fields rather than rename.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class DailyInputs:
    """User-supplied inputs for filing one daily note."""

    target: str  # vault-relative path or bare basename (with or without .md)


@dataclass
class DailyPlan:
    """What the workflow decided to do (populated even on dry-run)."""

    source: str | None = None  # vault-relative posix
    destination: str | None = None  # vault-relative posix
    date: str | None = None  # ISO YYYY-MM-DD
    h1_inserted: bool = False
    frontmatter_migrated: bool = False
    already_at_destination: bool = False


@dataclass
class DailyResult:
    """Result of one ``pqn-daily`` invocation."""

    vault: str
    apply: bool
    ok: bool = True
    plan: DailyPlan = field(default_factory=DailyPlan)
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

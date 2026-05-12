"""Public JSON contract for ``pqn-validate`` results.

Stable across releases — agents (Phase 7) and humans both consume this.
Add fields rather than rename.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["error", "warning", "info"]


@dataclass
class ValidateIssue:
    """One thing the validator flagged.

    ``check`` is the stable id of the check (e.g. ``filename_uniqueness``),
    not the human title. ``path`` is vault-relative POSIX. For checks that
    span multiple files (filename collisions) ``path`` is one of the
    colliding files; ``related`` lists the others.
    """

    check: str
    severity: Severity
    path: str
    message: str
    line: int | None = None
    related: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidateReport:
    """Top-level result the CLI emits."""

    vault: str
    files_scanned: int = 0
    checks_run: list[str] = field(default_factory=list)
    issues: list[ValidateIssue] = field(default_factory=list)

    @property
    def errors(self) -> list[ValidateIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidateIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": self.vault,
            "files_scanned": self.files_scanned,
            "checks_run": list(self.checks_run),
            "summary": {
                "total_issues": len(self.issues),
                "errors": len(self.errors),
                "warnings": len(self.warnings),
            },
            "issues": [asdict(i) for i in self.issues],
        }

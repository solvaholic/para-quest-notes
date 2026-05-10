"""Public JSON contract for ``pqn-ingest`` results.

This is the interface agents (Phase 7) and humans both consume. Keep
the field names stable; add new fields rather than rename.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Decisions:
    para_type: str | None = None
    quests: list[str] = field(default_factory=list)
    filename: str | None = None
    destination: str | None = None  # vault-relative posix path


@dataclass
class AppliedChange:
    moved_from: str
    moved_to: str
    attachments_moved: list[tuple[str, str]] = field(default_factory=list)
    wikilinks_rewritten: list[dict[str, Any]] = field(default_factory=list)
    frontmatter_updated: bool = False


@dataclass
class FileResult:
    """Result of ingesting one inbox file."""

    source: str  # vault-relative posix path
    ok: bool = True
    decisions: Decisions = field(default_factory=Decisions)
    applied: bool = False
    change: AppliedChange | None = None
    escalation: dict[str, Any] | None = None
    error: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # asdict turns tuples into lists already; keep change=None vs {}.
        if self.change is None:
            d["change"] = None
        return d


@dataclass
class IngestResult:
    """Top-level wrapper the CLI emits."""

    vault: str
    run_id: str
    apply: bool = False
    files: list[FileResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": self.vault,
            "run_id": self.run_id,
            "apply": self.apply,
            "files": [f.to_dict() for f in self.files],
        }

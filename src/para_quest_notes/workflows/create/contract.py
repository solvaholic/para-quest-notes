"""Public JSON contract for ``pqn-create`` results.

Stable across releases. Other agents (Phase 7) and humans both consume
this. Add fields rather than rename.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ParaType = Literal["project", "area", "resource"]
QuestKind = Literal["main", "side", "none"]
DestinationMode = Literal["canonical", "inbox"]


@dataclass
class CreateInputs:
    """User-supplied inputs for creating one note."""

    title: str
    type: ParaType
    quest: QuestKind = "none"
    supports: list[str] | None = None
    sub_path: str | None = None
    source_url: str | None = None
    body: str | None = None  # rendered stdin body; replaces templates and the skeleton
    template: str | None = None  # whole-note template name or path
    merge_template: bool = False


@dataclass
class TemplateMergePlan:
    """Provenance and lossless-routing accounting for an explicit merge."""

    status: Literal["failed", "deferred", "merged"] = "failed"
    template: str | None = None
    input_blocks: int | None = None
    routed_blocks: int | None = None
    unsorted_blocks: int | None = None


@dataclass
class CreatePlan:
    """What the workflow decided to do (populated even on dry-run)."""

    filename: str | None = None
    destination: str | None = None  # vault-relative posix path
    destination_mode: DestinationMode | None = None
    frontmatter: dict[str, Any] = field(default_factory=dict)
    body_source: str | None = None
    template_merge: TemplateMergePlan | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class CreateResult:
    """Result of one ``pqn-create`` invocation."""

    vault: str
    apply: bool
    ok: bool = True
    plan: CreatePlan = field(default_factory=CreatePlan)
    written: bool = False
    escalation: dict[str, Any] | None = None
    error: str | None = None
    run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": self.vault,
            "apply": self.apply,
            "ok": self.ok,
            "plan": asdict(self.plan),
            "written": self.written,
            "escalation": self.escalation,
            "error": self.error,
            "run_id": self.run_id,
        }

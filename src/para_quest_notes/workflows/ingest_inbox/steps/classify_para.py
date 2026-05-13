"""Step 2: classify_para (LLM).

Picks one of ``project | area | resource``. Schema:
``{"type": str, "confidence": float, "reason": str}``.
"""

from __future__ import annotations

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import Prompt
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.ingest_inbox.steps._llm import (
    call_llm_json,
    confidence_ok,
    require,
)
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanResult

VALID_TYPES = ("project", "area", "resource")
BODY_PREVIEW_CHARS = 2000


class ClassifyPara:
    name = "classify_para"

    def __init__(self, prompt: Prompt, *, model: str | None = None):
        self.prompt = prompt
        self.model = model

    def run(self, ctx: StepContext) -> StepResult:
        scan: ScanResult = ctx.scratchpad["scan"]
        preset_type = scan.parsed.frontmatter.get("type")
        if isinstance(preset_type, str):
            normalized = preset_type.strip().lower()
            if normalized in VALID_TYPES:
                ctx.scratchpad["para_type"] = normalized
                ctx.scratchpad["para_reason"] = "used pre-set type from frontmatter"
                return StepResult(
                    name=self.name,
                    output={
                        "type": normalized,
                        "confidence": 1.0,
                        "reason": "used pre-set type from frontmatter",
                        "skipped": True,
                    },
                    meta={"type": normalized, "source": "frontmatter"},
                )

        body_preview = scan.parsed.body.strip()[:BODY_PREVIEW_CHARS]
        parsed = call_llm_json(
            ctx_llm=ctx.llm,
            prompt=self.prompt,
            render_vars={
                "title": scan.title,
                "body": body_preview or "(empty)",
            },
            step_name=self.name,
            model=self.model,
        )
        para_type = str(require(parsed, "type", step=self.name, expected="string"))
        confidence = require(parsed, "confidence", step=self.name, expected="number")
        reason = str(parsed.get("reason", ""))

        if para_type not in VALID_TYPES:
            raise EscalateToUser(
                step=self.name,
                reason=f"LLM returned unknown PARA type {para_type!r}",
                options=[{"type": t} for t in VALID_TYPES],
                context={"reason": reason},
            )
        if not confidence_ok(confidence):
            raise EscalateToUser(
                step=self.name,
                reason="low confidence in PARA classification",
                options=[{"type": t} for t in VALID_TYPES],
                context={"type": para_type, "confidence": confidence, "reason": reason},
            )

        ctx.scratchpad["para_type"] = para_type
        ctx.scratchpad["para_reason"] = reason
        return StepResult(
            name=self.name,
            output={"type": para_type, "confidence": confidence, "reason": reason},
            meta={"type": para_type, "confidence": confidence},
        )

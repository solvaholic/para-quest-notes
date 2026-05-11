"""Step 3: pick_quest (LLM).

Picks one or more Quests from the vault's declared Main + Side Quests.
Skipped for resources (the spec makes ``supports`` optional there).

Reads the Quest list from ``ctx.scratchpad['quests']`` (set by the
pipeline once per run, since vault discovery is shared across files).
"""

from __future__ import annotations

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import Prompt
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.quests import Quest
from para_quest_notes.workflows.ingest_inbox.steps._llm import (
    call_llm_json,
    confidence_ok,
    require,
)
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanResult

BODY_PREVIEW_CHARS = 2000


class PickQuest:
    name = "pick_quest"

    def __init__(self, prompt: Prompt, *, model: str | None = None):
        self.prompt = prompt
        self.model = model

    def run(self, ctx: StepContext) -> StepResult:
        para_type = ctx.scratchpad.get("para_type")
        scan: ScanResult = ctx.scratchpad["scan"]

        # Resources don't require Quests per notes-system.md rule 3.
        if para_type == "resource":
            ctx.scratchpad["quests"] = []
            return StepResult(
                name=self.name,
                output={"quests": [], "skipped": True},
                meta={"skipped": "resource"},
            )

        quests: list[Quest] = ctx.scratchpad.get("vault_quests", [])
        if not quests:
            raise EscalateToUser(
                step=self.name,
                reason="vault declares no Main or Side Quests",
                options=[],
                context={"hint": "add quest: main or quest: side to areas/*.md"},
            )

        catalog = "\n".join(f"- {q.name} ({q.quest_kind})" for q in quests)
        valid_names = {q.name for q in quests}

        parsed = call_llm_json(
            ctx_llm=ctx.llm,
            prompt=self.prompt,
            render_vars={
                "title": scan.title,
                "body": scan.parsed.body.strip()[:BODY_PREVIEW_CHARS] or "(empty)",
                "para_type": para_type or "unknown",
                "quest_catalog": catalog,
            },
            step_name=self.name,
            model=self.model,
        )
        raw_quests = require(parsed, "quests", step=self.name, expected="array of strings")
        confidence = require(parsed, "confidence", step=self.name, expected="number")
        reason = str(parsed.get("reason", ""))

        if not isinstance(raw_quests, list) or not all(isinstance(q, str) for q in raw_quests):
            raise EscalateToUser(
                step=self.name,
                reason="LLM 'quests' field was not a list of strings",
                options=[{"quest": q.name} for q in quests],
                context={"raw": raw_quests},
            )

        picked = [q.strip() for q in raw_quests if q.strip()]
        unknown = [q for q in picked if q not in valid_names]
        if unknown:
            raise EscalateToUser(
                step=self.name,
                reason=f"LLM picked unknown Quest(s): {unknown}",
                options=[{"quest": q.name} for q in quests],
                context={"picked": picked, "reason": reason},
            )
        if not picked:
            raise EscalateToUser(
                step=self.name,
                reason="no defensible Quest match",
                options=[{"quest": q.name} for q in quests],
                context={"reason": reason},
            )
        if not confidence_ok(confidence):
            raise EscalateToUser(
                step=self.name,
                reason="low confidence in Quest pick",
                options=[{"quest": q.name} for q in quests],
                context={"picked": picked, "confidence": confidence, "reason": reason},
            )

        ctx.scratchpad["quests"] = picked
        return StepResult(
            name=self.name,
            output={"quests": picked, "confidence": confidence, "reason": reason},
            meta={"quests": picked, "confidence": confidence},
        )

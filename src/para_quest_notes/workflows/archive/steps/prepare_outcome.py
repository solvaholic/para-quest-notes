"""Step 5: prepare_outcome (pure).

Decides what to do about the ``## Outcome`` section:

* If the body already contains an ``## Outcome`` (or ``# Outcome``)
  heading, leave it alone. Pass-through; record ``outcome_action: "kept"``.
* If the user supplied ``--outcome "text"``, plan to insert it as a new
  ``## Outcome`` section just before the body's trailing whitespace.
  Record ``outcome_action: "inserted"``.
* If the body has no ``## Outcome`` and the user supplied nothing,
  escalate. No LLM in v0.1 — the user provides the prose.
"""

from __future__ import annotations

import re

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult

_OUTCOME_HEADING = re.compile(r"^#{1,6}\s+Outcome\s*$", re.MULTILINE)


class PrepareOutcome:
    name = "prepare_outcome"

    def __init__(self, *, outcome: str | None):
        self.outcome = outcome

    def run(self, ctx: StepContext) -> StepResult:
        split = ctx.scratchpad["split"]
        body: str = split.body
        if _OUTCOME_HEADING.search(body):
            ctx.scratchpad["outcome_action"] = "kept"
            ctx.scratchpad["outcome_text"] = None
            return StepResult(
                name=self.name,
                output={"action": "kept"},
            )
        if self.outcome is None or not self.outcome.strip():
            raise EscalateToUser(
                step=self.name,
                reason=(
                    "note has no '## Outcome' section; pass --outcome \"...\" "
                    "with a brief summary of what came of this Project"
                ),
                options=[],
                context={"source": ctx.scratchpad["source_rel"]},
            )
        ctx.scratchpad["outcome_action"] = "inserted"
        ctx.scratchpad["outcome_text"] = self.outcome.strip()
        return StepResult(
            name=self.name,
            output={"action": "inserted"},
        )

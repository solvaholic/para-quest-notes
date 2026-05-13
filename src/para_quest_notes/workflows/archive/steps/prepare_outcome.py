"""Step 5: prepare_outcome (pure).

Decides what to do about the ``## Outcome`` section:

* If the body already contains an ``## Outcome`` (or ``# Outcome``)
  heading, leave it alone. Pass-through; record ``outcome_action: "kept"``.
* If the user supplied ``--outcome "text"``, plan to insert it as a new
  ``## Outcome`` section just before the body's trailing whitespace.
  Record ``outcome_action: "provided"``.
* If the body has no ``## Outcome`` and ``--generate-outcome`` is set,
  dry-run records ``"will_generate"``; apply defers to the LLM step.
* Otherwise escalate and ask the user for ``--outcome``.
"""

from __future__ import annotations

import re

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult

_OUTCOME_HEADING = re.compile(r"^#{1,6}\s+Outcome\s*$", re.MULTILINE)


class PrepareOutcome:
    name = "prepare_outcome"

    def __init__(self, *, outcome: str | None, generate_outcome: bool = False, apply: bool = False):
        self.outcome = outcome
        self.generate_outcome = generate_outcome
        self.apply = apply

    def run(self, ctx: StepContext) -> StepResult:
        split = ctx.scratchpad["split"]
        body: str = split.body
        if _OUTCOME_HEADING.search(body):
            ctx.scratchpad["needs_generate_outcome"] = False
            ctx.scratchpad["outcome_action"] = "kept"
            ctx.scratchpad["outcome_text"] = None
            return StepResult(name=self.name, output={"action": "kept"})

        if self.outcome is not None and self.outcome.strip():
            ctx.scratchpad["needs_generate_outcome"] = False
            ctx.scratchpad["outcome_action"] = "provided"
            ctx.scratchpad["outcome_text"] = self.outcome.strip()
            return StepResult(name=self.name, output={"action": "provided"})

        if self.generate_outcome:
            if self.apply:
                ctx.scratchpad["needs_generate_outcome"] = True
                ctx.scratchpad["outcome_action"] = "none"
                ctx.scratchpad["outcome_text"] = None
                return StepResult(name=self.name, output={"action": "generate_requested"})
            ctx.scratchpad["needs_generate_outcome"] = False
            ctx.scratchpad["outcome_action"] = "will_generate"
            ctx.scratchpad["outcome_text"] = None
            return StepResult(name=self.name, output={"action": "will_generate"})

        ctx.scratchpad["needs_generate_outcome"] = False
        ctx.scratchpad["outcome_action"] = "required"
        ctx.scratchpad["outcome_text"] = None
        raise EscalateToUser(
            step=self.name,
            reason=(
                "note has no '## Outcome' section; pass --outcome \"...\" "
                "or re-run with --generate-outcome --apply"
            ),
            options=[],
            context={"source": ctx.scratchpad["source_rel"]},
        )

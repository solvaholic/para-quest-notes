"""Step 5: plan_destination (pure).

Flat layout: ``projects/``, ``areas/``, ``resources/`` directly under
the vault root. PLAN.md decision; mirroring an existing sub-structure
is a future enhancement (TODO).
"""

from __future__ import annotations

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult

# TODO(enhancement): if a sensible sub-structure exists in the vault
# (e.g., the picked Quest already has its own dir under projects/),
# mirror it instead of dropping at the root. Today this lives flat.
PARA_DIR = {
    "project": "projects",
    "area": "areas",
    "resource": "resources",
}


class PlanDestination:
    name = "plan_destination"

    def run(self, ctx: StepContext) -> StepResult:
        para_type = ctx.scratchpad.get("para_type")
        filename = ctx.scratchpad.get("filename")
        if not para_type or not filename:
            raise EscalateToUser(
                step=self.name,
                reason="missing para_type or filename in scratchpad",
                options=[],
                context={"para_type": para_type, "filename": filename},
            )
        top = PARA_DIR.get(para_type)
        if top is None:
            raise EscalateToUser(
                step=self.name,
                reason=f"no destination dir for para_type={para_type!r}",
                options=[],
                context={},
            )
        dest = f"{top}/{filename}"
        ctx.scratchpad["destination"] = dest
        return StepResult(name=self.name, output={"destination": dest}, meta={"destination": dest})

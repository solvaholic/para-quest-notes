"""Step 4: decide_task_action (pure, escalation gate).

If the note has open or in-progress tasks and the user didn't pass
``--cancel-open-tasks``, escalate with the offending lines surfaced.
That mirrors the legacy SKILL's interactive prompt: the CLI can't
pause for a choice, so the user picks one by re-invoking with or
without the flag.
"""

from __future__ import annotations

from typing import Any

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult


class DecideTaskAction:
    name = "decide_task_action"

    def __init__(self, *, cancel_open_tasks: bool):
        self.cancel_open_tasks = cancel_open_tasks

    def run(self, ctx: StepContext) -> StepResult:
        tasks: list[dict[str, Any]] = ctx.scratchpad.get("open_tasks", [])
        if tasks and not self.cancel_open_tasks:
            raise EscalateToUser(
                step=self.name,
                reason=(
                    f"{len(tasks)} open task(s) in this Project; close them in "
                    "the editor or re-run with --cancel-open-tasks"
                ),
                options=[
                    {"line": t["line"], "state": t["state"], "text": t["text"]} for t in tasks
                ],
                context={"source": ctx.scratchpad["source_rel"]},
            )
        ctx.scratchpad["will_cancel_tasks"] = bool(tasks) and self.cancel_open_tasks
        return StepResult(
            name=self.name,
            output={
                "open_tasks": len(tasks),
                "will_cancel": ctx.scratchpad["will_cancel_tasks"],
            },
        )

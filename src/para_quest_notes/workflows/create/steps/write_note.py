"""Step 5: write_note (``--apply`` gated, refuses to overwrite).

Dry-run by default. With ``apply=True`` the shared creation substrate
atomically publishes the composed content without replacing a concurrent
winner.
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.creation import publish_new_note


class WriteNote:
    name = "write_note"

    def __init__(self, *, apply: bool):
        self.apply = apply

    def run(self, ctx: StepContext) -> StepResult:
        dest_abs: Path = ctx.scratchpad["destination_abs"]
        destination: str = ctx.scratchpad["destination"]
        content: str = ctx.scratchpad["content"]

        if not self.apply:
            return StepResult(
                name=self.name,
                output={"written": False, "destination": destination, "bytes": len(content)},
                meta={"applied": False},
            )

        if dest_abs.exists():
            # Step 3 should have caught this; re-check defensively in case
            # of a TOCTOU race between collision check and write.
            raise EscalateToUser(
                step=self.name,
                reason=f"destination appeared between collision check and write: {destination}",
                options=[],
                context={"destination": destination},
            )

        try:
            publish_new_note(dest_abs, content)
        except FileExistsError:
            raise EscalateToUser(
                step=self.name,
                reason=f"destination appeared between collision check and write: {destination}",
                options=[],
                context={"destination": destination},
            ) from None

        return StepResult(
            name=self.name,
            output={"written": True, "destination": destination, "bytes": len(content)},
            meta={"applied": True},
        )

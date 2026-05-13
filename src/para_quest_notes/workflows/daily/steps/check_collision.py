"""Step 5: check_collision (pure).

Refuse to overwrite the destination, then delegate basename uniqueness
to ``validate.api.check_basename_available`` with ``ignore_path=source``
so the source itself doesn't count as a collision (otherwise filing
from ``inbox/2026-05-12.md`` would always escalate against itself).

When ``already_at_destination`` is set, the source *is* the destination
— skip both checks and return successfully so re-runs are a no-op.
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.validate.api import check_basename_available


class CheckCollision:
    name = "check_collision"

    def run(self, ctx: StepContext) -> StepResult:
        if ctx.vault is None:
            raise EscalateToUser(
                step=self.name,
                reason="no vault path resolved",
                options=[],
                context={},
            )
        already: bool = ctx.scratchpad.get("already_at_destination", False)
        destination: str = ctx.scratchpad["destination_rel"]
        dest_abs: Path = ctx.scratchpad["destination_abs"]
        source_abs: Path = ctx.scratchpad["source_abs"]
        date_iso: str = ctx.scratchpad["date_iso"]
        basename = f"{date_iso}.md"

        if already:
            return StepResult(
                name=self.name,
                output={"skipped": True, "reason": "already_at_destination"},
                meta={"already_at_destination": True},
            )

        if dest_abs.exists():
            raise EscalateToUser(
                step=self.name,
                reason=f"destination already exists: {destination}",
                options=[{"existing": destination}],
                context={"destination": destination},
            )

        issues = check_basename_available(
            ctx.vault,
            basename,
            ignore_path=source_abs,
        )
        if issues:
            issue = issues[0]
            raise EscalateToUser(
                step=self.name,
                reason="basename collides with existing note(s)",
                options=[{"existing": rel} for rel in issue.related],
                context={"validate_message": issue.message, "basename": basename},
            )
        return StepResult(
            name=self.name,
            output={"skipped": False, "collisions": []},
        )

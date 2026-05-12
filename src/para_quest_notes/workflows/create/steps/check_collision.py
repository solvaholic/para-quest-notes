"""Step 3: check_collision (pure).

Delegates to :func:`para_quest_notes.workflows.validate.api.check_basename_available`
— the same collision logic ``pqn-ingest`` uses. Wikilinks resolve by
basename, so a duplicate basename anywhere in the vault is enough to
make ``[[Title]]`` ambiguous and is treated as a collision.

We also refuse to overwrite any existing file at the planned path,
even if the basename happens to be unique elsewhere (Step 5 won't
overwrite either; failing here gives the user a clearer message and
avoids the partial-write window).
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
        filename: str = ctx.scratchpad["filename"]
        destination: str = ctx.scratchpad["destination"]
        dest_abs: Path = ctx.scratchpad["destination_abs"]

        if dest_abs.exists():
            raise EscalateToUser(
                step=self.name,
                reason=f"destination already exists: {destination}",
                options=[{"destination": destination}],
                context={"existing": destination},
            )

        issues = check_basename_available(ctx.vault, filename)
        if issues:
            issue = issues[0]
            raise EscalateToUser(
                step=self.name,
                reason="filename collides with existing note(s)",
                options=[{"existing": rel} for rel in issue.related],
                context={"validate_message": issue.message, "filename": filename},
            )
        return StepResult(
            name=self.name,
            output={"filename": filename, "collisions": []},
        )

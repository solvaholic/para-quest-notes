"""Step 7: move_file (``--apply`` gated).

Dry-run by default. With ``apply=True``:

* When ``already_at_destination`` and content didn't change, do
  nothing — idempotent re-run is a no-op success.
* When ``already_at_destination`` and content *did* change (H1 added
  or backmatter migrated), rewrite the file in place atomically.
* Otherwise: refuse to overwrite the destination (defensive re-check),
  write composed content via sibling temp + ``os.replace``, then
  ``unlink`` the source. Write-first / remove-second matches
  ``pqn-archive`` so a crash leaves both copies, not neither.
"""

from __future__ import annotations

import os
from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult


class MoveFile:
    name = "move_file"

    def __init__(self, *, apply: bool):
        self.apply = apply

    def run(self, ctx: StepContext) -> StepResult:
        source: Path = ctx.scratchpad["source_abs"]
        dest_abs: Path = ctx.scratchpad["destination_abs"]
        dest_rel: str = ctx.scratchpad["destination_rel"]
        content: str = ctx.scratchpad["content"]
        content_changed: bool = ctx.scratchpad.get("content_changed", True)
        already: bool = ctx.scratchpad.get("already_at_destination", False)

        if not self.apply:
            return StepResult(
                name=self.name,
                output={
                    "moved": False,
                    "destination": dest_rel,
                    "bytes": len(content.encode("utf-8")),
                },
                meta={"applied": False},
            )

        if already:
            if content_changed:
                # Rewrite in place atomically; no source removal.
                tmp = dest_abs.with_name(f".{dest_abs.name}.tmp")
                tmp.write_text(content, encoding="utf-8")
                os.replace(tmp, dest_abs)
            return StepResult(
                name=self.name,
                output={
                    "moved": False,
                    "destination": dest_rel,
                    "rewrote_in_place": content_changed,
                },
                meta={"applied": True, "already_at_destination": True},
            )

        if dest_abs.exists():
            raise EscalateToUser(
                step=self.name,
                reason=f"destination already exists: {dest_rel}",
                options=[],
                context={"destination": dest_rel},
            )

        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest_abs.with_name(f".{dest_abs.name}.tmp")
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, dest_abs)
        source.unlink()

        return StepResult(
            name=self.name,
            output={"moved": True, "destination": dest_rel},
            meta={"applied": True},
        )

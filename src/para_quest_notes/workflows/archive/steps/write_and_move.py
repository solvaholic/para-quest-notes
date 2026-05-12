"""Step 7: write_and_move (``--apply`` gated).

Dry-run by default. With ``apply=True``:

* Refuse to overwrite the archive destination (defensive re-check,
  even though compose_archive computed the path from the source).
* Write the composed content to a sibling temp path under the
  destination directory, then ``os.replace`` it into place.
* Remove the source file.

The order — write archive first, then remove source — means a crash
between the two leaves *both* copies on disk rather than dropping
the note. The user can resolve the duplicate manually.
"""

from __future__ import annotations

import os
from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult


class WriteAndMove:
    name = "write_and_move"

    def __init__(self, *, apply: bool):
        self.apply = apply

    def run(self, ctx: StepContext) -> StepResult:
        source: Path = ctx.scratchpad["source_abs"]
        dest_abs: Path = ctx.scratchpad["destination_abs"]
        dest_rel: str = ctx.scratchpad["destination_rel"]
        content: str = ctx.scratchpad["content"]

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

        if dest_abs.exists():
            raise EscalateToUser(
                step=self.name,
                reason=f"archive destination already exists: {dest_rel}",
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

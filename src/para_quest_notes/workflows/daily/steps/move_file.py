"""Step 7: move_file (``--apply`` gated).

Dry-run by default. With ``apply=True``:

* When ``already_at_destination`` and content didn't change, do
  nothing — idempotent re-run is a no-op success.
* When ``already_at_destination`` and content *did* change (H1 added
  or backmatter migrated), rewrite the file in place atomically.
* When authoring a missing date, atomically publish the canonical note
  without replacing a destination created by another process.
* Otherwise: refuse to overwrite the destination (defensive re-check),
  publish composed content without replacement, then
  ``unlink`` the source. Write-first / remove-second matches
  ``pqn-archive`` so a crash leaves both copies, not neither.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult


class MoveFile:
    name = "move_file"

    def __init__(self, *, apply: bool):
        self.apply = apply

    def run(self, ctx: StepContext) -> StepResult:
        source: Path | None = ctx.scratchpad["source_abs"]
        dest_abs: Path = ctx.scratchpad["destination_abs"]
        dest_rel: str = ctx.scratchpad["destination_rel"]
        content: str = ctx.scratchpad["content"]
        content_changed: bool = ctx.scratchpad.get("content_changed", True)
        already: bool = ctx.scratchpad.get("already_at_destination", False)
        creating: bool = ctx.scratchpad.get("creating_missing", False)

        if not self.apply:
            return StepResult(
                name=self.name,
                output={
                    "moved": False,
                    "created": False,
                    "destination": dest_rel,
                    "bytes": len(content.encode("utf-8")),
                },
                meta={"applied": False},
            )

        if creating:
            if dest_abs.exists():
                self._destination_exists(dest_rel)
            dest_abs.parent.mkdir(parents=True, exist_ok=True)
            self._publish_without_replace(dest_abs, dest_rel, content)
            return StepResult(
                name=self.name,
                output={"moved": False, "created": True, "destination": dest_rel},
                meta={"applied": True, "created": True},
            )

        if already:
            if content_changed:
                # Rewrite in place atomically; no source removal.
                self._replace(dest_abs, content)
            return StepResult(
                name=self.name,
                output={
                    "moved": False,
                    "created": False,
                    "destination": dest_rel,
                    "rewrote_in_place": content_changed,
                },
                meta={"applied": True, "already_at_destination": True},
            )

        if dest_abs.exists():
            self._destination_exists(dest_rel)

        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        self._publish_without_replace(dest_abs, dest_rel, content)
        if source is None:  # pragma: no cover - guarded by the creating branch
            raise RuntimeError("daily filing source is missing")
        source.unlink()

        return StepResult(
            name=self.name,
            output={"moved": True, "created": False, "destination": dest_rel},
            meta={"applied": True},
        )

    def _publish_without_replace(self, destination: Path, dest_rel: str, content: str) -> None:
        """Publish complete content atomically, refusing a concurrent winner."""
        temp = self._write_unique_temp(destination, content)
        try:
            os.link(temp, destination)
        except FileExistsError:
            self._destination_exists(dest_rel)
        finally:
            temp.unlink(missing_ok=True)

    def _replace(self, destination: Path, content: str) -> None:
        temp = self._write_unique_temp(destination, content)
        try:
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _write_unique_temp(destination: Path, content: str) -> Path:
        while True:
            temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            except FileExistsError:  # pragma: no cover - UUID collision defense
                continue
            complete = False
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                complete = True
            finally:
                if not complete:
                    temp.unlink(missing_ok=True)
            return temp

    def _destination_exists(self, dest_rel: str) -> None:
        raise EscalateToUser(
            step=self.name,
            reason=f"destination already exists: {dest_rel}",
            options=[],
            context={"destination": dest_rel},
        )

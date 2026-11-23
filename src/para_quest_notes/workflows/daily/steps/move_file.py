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
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult


@dataclass(frozen=True)
class SourceSnapshot:
    """Source bytes and identity captured before composition begins."""

    content: bytes
    device: int
    inode: int
    mode: int

    @classmethod
    def capture(cls, path: Path) -> SourceSnapshot:
        with path.open("rb") as handle:
            content = handle.read()
            source_stat = os.fstat(handle.fileno())
        return cls(
            content=content,
            device=source_stat.st_dev,
            inode=source_stat.st_ino,
            mode=stat.S_IMODE(source_stat.st_mode),
        )

    def matches(self, path: Path) -> bool:
        try:
            current = self.capture(path)
            path_stat = path.stat()
        except FileNotFoundError:
            return False
        return (
            current.device == path_stat.st_dev
            and current.inode == path_stat.st_ino
            and current.device == self.device
            and current.inode == self.inode
            and current.mode == self.mode
            and current.content == self.content
        )


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
            self._publish_without_replace(dest_abs, dest_rel, content, mode=None)
            return StepResult(
                name=self.name,
                output={"moved": False, "created": True, "destination": dest_rel},
                meta={"applied": True, "created": True},
            )

        if already:
            if content_changed:
                if source is None:  # pragma: no cover - guarded by prior steps
                    raise RuntimeError("daily filing source is missing")
                snapshot = self._source_snapshot(ctx)
                self._verify_source_unchanged(ctx, source, snapshot)
                # Rewrite in place atomically; no source removal.
                self._replace(dest_abs, content, mode=snapshot.mode)
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

        if source is None:  # pragma: no cover - guarded by the creating branch
            raise RuntimeError("daily filing source is missing")
        snapshot = self._source_snapshot(ctx)
        self._verify_source_unchanged(ctx, source, snapshot)
        dest_abs.parent.mkdir(parents=True, exist_ok=True)
        self._publish_without_replace(dest_abs, dest_rel, content, mode=snapshot.mode)
        self._verify_source_unchanged(ctx, source, snapshot, destination_written=True)
        source.unlink()

        return StepResult(
            name=self.name,
            output={"moved": True, "created": False, "destination": dest_rel},
            meta={"applied": True},
        )

    def _publish_without_replace(
        self,
        destination: Path,
        dest_rel: str,
        content: str,
        *,
        mode: int | None,
    ) -> None:
        """Publish complete content atomically, refusing a concurrent winner."""
        temp = self._write_unique_temp(destination, content, mode=mode)
        try:
            os.link(temp, destination)
        except FileExistsError:
            self._destination_exists(dest_rel)
        finally:
            temp.unlink(missing_ok=True)

    def _replace(self, destination: Path, content: str, *, mode: int) -> None:
        temp = self._write_unique_temp(destination, content, mode=mode)
        try:
            os.replace(temp, destination)
        finally:
            temp.unlink(missing_ok=True)

    @staticmethod
    def _write_unique_temp(destination: Path, content: str, *, mode: int | None) -> Path:
        while True:
            temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            except FileExistsError:  # pragma: no cover - UUID collision defense
                continue
            complete = False
            try:
                if mode is not None:
                    os.fchmod(descriptor, mode)
                with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                complete = True
            finally:
                if not complete:
                    temp.unlink(missing_ok=True)
            return temp

    @staticmethod
    def _source_snapshot(ctx: StepContext) -> SourceSnapshot:
        snapshot = ctx.scratchpad.get("source_snapshot")
        if not isinstance(snapshot, SourceSnapshot):
            raise RuntimeError("daily filing source snapshot is missing")
        return snapshot

    @staticmethod
    def _verify_source_unchanged(
        ctx: StepContext,
        source: Path,
        snapshot: SourceSnapshot,
        *,
        destination_written: bool = False,
    ) -> None:
        if snapshot.matches(source):
            return
        source_rel = ctx.scratchpad.get("source_rel") or str(source)
        detail = (
            "the planned destination was retained and the edited source was not removed"
            if destination_written
            else "no vault write was performed"
        )
        raise EscalateToUser(
            step=MoveFile.name,
            reason=f"source changed during daily composition; {detail}",
            options=[],
            context={
                "source": source_rel,
                "destination_written": destination_written,
            },
        )

    def _destination_exists(self, dest_rel: str) -> None:
        raise EscalateToUser(
            step=self.name,
            reason=f"destination already exists: {dest_rel}",
            options=[],
            context={"destination": dest_rel},
        )

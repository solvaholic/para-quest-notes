"""Step 4: compute_destination (pure).

Canonical home: ``resources/daily_notes/YYYY/MM/YYYY-MM-DD.md``.
Year/month come from the *filename*, not the filesystem mtime — the
filename is the source of truth for what date a daily note represents.

Sets ``already_at_destination`` when the source is already exactly at
this path, so downstream steps can short-circuit (no collision check
needed; ``move_file`` is a no-op).
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.step import StepContext, StepResult


class ComputeDestination:
    name = "compute_destination"

    def run(self, ctx: StepContext) -> StepResult:
        vault: Path = ctx.vault  # type: ignore[assignment]
        source_abs: Path | None = ctx.scratchpad["source_abs"]
        source_rel: str | None = ctx.scratchpad["source_rel"]
        date_iso: str = ctx.scratchpad["date_iso"]
        year: str = ctx.scratchpad["date_year"]
        month: str = ctx.scratchpad["date_month"]

        dest_rel = Path("resources") / "daily_notes" / year / month / f"{date_iso}.md"
        dest_rel_posix = dest_rel.as_posix()
        dest_abs = vault / dest_rel

        already = (
            source_abs is not None and source_abs.resolve() == dest_abs.resolve()
        ) or source_rel == dest_rel_posix

        ctx.scratchpad["destination_abs"] = dest_abs
        ctx.scratchpad["destination_rel"] = dest_rel_posix
        ctx.scratchpad["already_at_destination"] = already
        return StepResult(
            name=self.name,
            output={
                "destination": dest_rel_posix,
                "already_at_destination": already,
            },
            meta={"destination": dest_rel_posix},
        )

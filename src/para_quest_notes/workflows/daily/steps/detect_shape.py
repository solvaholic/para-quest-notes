"""Step 2: detect_shape (pure).

The basename must be ``YYYY-MM-DD.md`` *and* parse as a real calendar
date. We reject e.g. ``2026-02-31.md`` here rather than discovering it
later when ``compute_destination`` divides into year/month bins.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult

_DAILY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")


class DetectShape:
    name = "detect_shape"

    def run(self, ctx: StepContext) -> StepResult:
        source: Path = ctx.scratchpad["source_abs"]
        basename = source.name
        m = _DAILY_RE.match(basename)
        if m is None:
            raise EscalateToUser(
                step=self.name,
                reason="filename does not match YYYY-MM-DD.md",
                options=[],
                context={"basename": basename},
            )
        year, month, day = (int(m.group(1)), int(m.group(2)), int(m.group(3)))
        try:
            iso = date(year, month, day).isoformat()
        except ValueError as exc:
            raise EscalateToUser(
                step=self.name,
                reason=f"filename is not a real calendar date: {exc}",
                options=[],
                context={"basename": basename},
            ) from exc

        ctx.scratchpad["date_iso"] = iso
        ctx.scratchpad["date_year"] = m.group(1)
        ctx.scratchpad["date_month"] = m.group(2)
        return StepResult(
            name=self.name,
            output={"date": iso},
            meta={"date": iso},
        )

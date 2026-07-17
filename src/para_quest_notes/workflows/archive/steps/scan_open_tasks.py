"""Step 3: scan_open_tasks (pure, fence-aware).

Walks the note body once and lists open and in-progress task lines
that aren't inside fenced code blocks. Obsidian Tasks treats ``[ ]``
as open and ``[/]`` as in-progress. ``[x]`` (complete) and ``[-]``
(cancelled) are not counted.

The fence-aware scan itself lives in :mod:`para_quest_notes.vault.tasks`
(shared with the read-only ``pqn-tasks`` reporter); this step filters
that scan to open/in-progress tasks and shapes them into the dict the
downstream cancellation step expects.

The result is the canonical candidate set: write_archive uses the
exact same line numbers when ``--cancel-open-tasks`` is set, so we
never rewrite something we didn't surface.
"""

from __future__ import annotations

from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.tasks import scan_tasks


def find_open_tasks(body: str) -> list[dict[str, object]]:
    """Return open/in-progress task lines outside fenced code blocks.

    Each entry: ``{"line": int (1-based body line), "state": " "|"/",
    "text": str, "bullet": str}``. The line number is into ``body``
    only — callers translate to file lines if they need to.
    """
    return [
        {
            "line": t.line,
            "state": t.state,
            "text": t.text,
            "bullet": t.bullet,
        }
        for t in scan_tasks(body)
        if t.is_open
    ]


class ScanOpenTasks:
    name = "scan_open_tasks"

    def run(self, ctx: StepContext) -> StepResult:
        split = ctx.scratchpad["split"]
        tasks = find_open_tasks(split.body)
        ctx.scratchpad["open_tasks"] = tasks
        return StepResult(
            name=self.name,
            output={"count": len(tasks), "tasks": tasks},
            meta={"count": len(tasks)},
        )

"""Step 3: scan_open_tasks (pure, fence-aware).

Walks the note body once and lists open and in-progress task lines
that aren't inside fenced code blocks. Obsidian Tasks treats ``[ ]``
as open and ``[/]`` as in-progress. ``[x]`` (complete) and ``[-]``
(cancelled) are not counted.

The result is the canonical candidate set: write_archive uses the
exact same line numbers when ``--cancel-open-tasks`` is set, so we
never rewrite something we didn't surface.
"""

from __future__ import annotations

import re

from para_quest_notes.adapter.step import StepContext, StepResult

# Matches ``- [ ] text`` and ``- [/] text`` (and ``* [ ]``, ``+ [ ]``).
# Leading whitespace is allowed; the bullet character is captured so we
# can preserve it when rewriting.
_TASK_LINE = re.compile(r"^([ \t]*[-*+] )\[([ /])\] (.*)$")
_FENCE = re.compile(r"^([ \t]*)(```|~~~)")


def find_open_tasks(body: str) -> list[dict[str, object]]:
    """Return open/in-progress task lines outside fenced code blocks.

    Each entry: ``{"line": int (1-based body line), "state": " "|"/",
    "text": str, "bullet": str}``. The line number is into ``body``
    only — callers translate to file lines if they need to.
    """
    found: list[dict[str, object]] = []
    in_fence = False
    fence_marker: str | None = None
    for idx, line in enumerate(body.splitlines(), start=1):
        m_fence = _FENCE.match(line)
        if m_fence is not None:
            marker = m_fence.group(2)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            # Either way, the fence line itself is never a task.
            continue
        if in_fence:
            continue
        m = _TASK_LINE.match(line)
        if m is None:
            continue
        found.append(
            {
                "line": idx,
                "state": m.group(2),
                "text": m.group(3),
                "bullet": m.group(1),
            }
        )
    return found


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

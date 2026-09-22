"""Compose one managed ``pqn-tasks`` roundup into a daily note."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import parse
from para_quest_notes.workflows.tasks.pipeline import scan_vault_tasks
from para_quest_notes.workflows.tasks.render import render_markdown

START_MARKER = "<!-- pqn-daily:task-roundup:start -->"
END_MARKER = "<!-- pqn-daily:task-roundup:end -->"

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_FENCE_CLOSE = re.compile(r"^ {0,3}(`+|~+)[ \t]*$")


@dataclass(frozen=True)
class _Marker:
    kind: str
    start: int
    end: int


class ComposeTaskRoundup:
    """Read tasks and update the candidate note content without writing."""

    name = "compose_task_roundup"

    def __init__(self, *, date_fields: Sequence[str], apply: bool):
        self.date_fields = list(date_fields)
        self.apply = apply

    def run(self, ctx: StepContext) -> StepResult:
        if ctx.vault is None:  # pragma: no cover - workflow always supplies it
            raise RuntimeError("daily task roundup requires a vault")

        date_iso: str = ctx.scratchpad["date_iso"]
        content: str = ctx.scratchpad["content"]
        report = scan_vault_tasks(
            ctx.vault,
            today=date.fromisoformat(date_iso),
            due_in=7,
            overdue_only=False,
            types=None,
            quest=None,
            group_by="due",
            date_fields=self.date_fields,
            include_archive=False,
            unscheduled="hide",
        )
        rendered = render_markdown(report, heading_level=2)
        region = f"{START_MARKER}\n{rendered}{END_MARKER}\n"

        parsed = parse(content)
        prefix = content[: len(content) - len(parsed.body)] if parsed.had_frontmatter else ""
        body, action = _merge_region(parsed.body, region)
        composed = prefix + body

        ctx.scratchpad["content"] = composed
        ctx.scratchpad["content_changed"] = bool(
            ctx.scratchpad.get("content_changed", False) or composed != content
        )

        summary = report.summary
        output = {
            "action": action,
            "applied": self.apply,
            "reference_date": report.reference_date,
            "due_in": report.due_in,
            "group_by": report.group_by,
            "date_fields": list(report.date_fields),
            "include_archive": report.include_archive,
            "unscheduled": "hide",
            "files_scanned": report.files_scanned,
            "summary": summary,
        }
        ctx.scratchpad["task_roundup"] = output
        return StepResult(
            name=self.name,
            output=output,
            meta={"action": action, "tasks": summary["total"]},
        )


def _merge_region(body: str, region: str) -> tuple[str, str]:
    markers, unclosed_fence = _markers_outside_fences(body)
    if not markers:
        if unclosed_fence:
            raise EscalateToUser(
                step=ComposeTaskRoundup.name,
                reason=(
                    "cannot append a managed task roundup while the note ends "
                    "inside an unclosed fenced code block"
                ),
                options=[],
                context={"unclosed_fence": True},
            )
        return _append_region(body, region), "insert"

    if len(markers) != 2 or [marker.kind for marker in markers] != ["start", "end"]:
        starts = sum(marker.kind == "start" for marker in markers)
        ends = sum(marker.kind == "end" for marker in markers)
        raise EscalateToUser(
            step=ComposeTaskRoundup.name,
            reason=(
                "managed task-roundup markers are ambiguous; expected exactly "
                "one start marker followed by one end marker"
            ),
            options=[],
            context={"start_markers": starts, "end_markers": ends},
        )

    start, end = markers
    existing = body[start.start : end.end]
    if existing == region:
        return body, "unchanged"
    return body[: start.start] + region + body[end.end :], "replace"


def _append_region(body: str, region: str) -> str:
    if not body:
        return region
    if body.endswith("\n\n"):
        return body + region
    if body.endswith("\n"):
        return body + "\n" + region
    return body + "\n\n" + region


def _markers_outside_fences(body: str) -> tuple[list[_Marker], bool]:
    markers: list[_Marker] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    offset = 0

    for line in body.splitlines(keepends=True):
        text = line.rstrip("\r\n")
        if in_fence:
            closed = _FENCE_CLOSE.match(text)
            if closed is not None:
                run = closed.group(1)
                if run[0] == fence_char and len(run) >= fence_len:
                    in_fence = False
            offset += len(line)
            continue

        opened = _FENCE_OPEN.match(text)
        if opened is not None:
            run = opened.group(1)
            info = opened.group(2)
            if run[0] == "`" and "`" in info:
                offset += len(line)
                continue
            in_fence = True
            fence_char = run[0]
            fence_len = len(run)
            offset += len(line)
            continue

        if text == START_MARKER:
            markers.append(_Marker("start", offset, offset + len(line)))
        elif text == END_MARKER:
            markers.append(_Marker("end", offset, offset + len(line)))
        offset += len(line)

    return markers, in_fence

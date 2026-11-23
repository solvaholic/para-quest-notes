"""Markdown rendering for ``pqn-tasks`` reports."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import PurePosixPath

from .contract import (
    BUCKET_ORDER,
    DATE_FIELDS,
    UNASSIGNED,
    TaskItem,
    TasksReport,
    UnscheduledMode,
)

_BUCKET_LABELS = {
    "overdue": "Overdue",
    "due_today": "Due today",
    "upcoming": "Upcoming",
    "unscheduled": "Unscheduled",
}

_DATE_EMOJI = {
    "due": "📅",
    "scheduled": "⏳",
    "start": "🛫",
}


def _wikilink(path: str) -> str:
    return f"[[{PurePosixPath(path).stem}]]"


def _render_task(
    task: TaskItem,
    *,
    show_bucket: bool,
    date_fields: Sequence[str],
) -> str:
    parts: list[str] = []
    if task.date_source is not None and task.effective_date is not None:
        parts.append(f"{task.date_source} {task.effective_date}")
    if show_bucket:
        parts.append(_BUCKET_LABELS[task.bucket].lower())

    if task.bucket == "unscheduled":
        untracked = [
            f"{_DATE_EMOJI[field]} {value}"
            for field in DATE_FIELDS
            if field not in date_fields and (value := getattr(task, field)) is not None
        ]
        if untracked:
            parts.append(f"untracked: {', '.join(untracked)}")

    suffix = f" ({', '.join(parts)})" if parts else ""
    return f"- {_wikilink(task.path)} {task.description}{suffix}"


def _grouped(report: TasksReport) -> list[tuple[str, list[TaskItem]]]:
    """Return ``(header, tasks)`` groups honoring ``report.group_by``."""
    if report.group_by == "due":
        groups: list[tuple[str, list[TaskItem]]] = []
        for bucket in BUCKET_ORDER:
            tasks = [task for task in report.tasks if task.bucket == bucket]
            if tasks:
                groups.append((_BUCKET_LABELS[bucket], tasks))
        return groups

    key_attr = "quests" if report.group_by == "quest" else "areas"
    buckets: dict[str, list[TaskItem]] = {}
    for task in report.tasks:
        keys = getattr(task, key_attr) or [UNASSIGNED]
        for key in keys:
            buckets.setdefault(key, []).append(task)

    def sort_key(name: str) -> tuple[int, str]:
        return (1, "") if name == UNASSIGNED else (0, name.lower())

    return [(name, buckets[name]) for name in sorted(buckets, key=sort_key)]


def render_markdown(
    report: TasksReport,
    *,
    unscheduled: UnscheduledMode = "hide",
    heading_level: int = 1,
) -> str:
    """Render a task report, optionally nested beneath existing headings."""
    if not 1 <= heading_level <= 5:
        raise ValueError("heading_level must be between 1 and 5")

    if unscheduled == "only":
        title = f"Unscheduled tasks as of {report.reference_date}"
        empty_message = "No open unscheduled tasks."
    else:
        horizon = f"within {report.due_in} day(s)"
        if report.due_in == 0:
            horizon = "today or overdue"
        title = f"Tasks as of {report.reference_date} ({horizon})"
        empty_message = "No open tasks due."

    title_prefix = "#" * heading_level
    group_prefix = "#" * (heading_level + 1)
    if not report.tasks:
        return f"{title_prefix} {title}\n\n{empty_message}\n"

    show_bucket = report.group_by != "due"
    lines = [f"{title_prefix} {title}", ""]
    for header, tasks in _grouped(report):
        lines.append(f"{group_prefix} {header} ({len(tasks)})")
        for task in tasks:
            lines.append(
                _render_task(
                    task,
                    show_bucket=show_bucket,
                    date_fields=report.date_fields,
                )
            )
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"

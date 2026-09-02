"""``pqn-tasks`` CLI entry point.

Read-only reporter: scans the vault for open tasks carrying Obsidian
Tasks due dates and prints what's overdue / due today / due soon. Text
output is markdown (plain ``-`` bullets, source note wikilinked) so a
roundup can be pasted into a daily note without re-parsing as live
tasks; ``--format json`` emits the structured contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import PurePosixPath

from para_quest_notes.adapter.cli import build_base_parser
from para_quest_notes.adapter.completion import (
    complete_quests,
    enable_completion,
    set_completer,
)
from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import ConfigError, VaultError
from para_quest_notes.adapter.vault import find_vault

from .contract import BUCKET_ORDER, DATE_FIELDS, UNASSIGNED, TaskItem, TasksReport
from .pipeline import scan_vault_tasks
from .settings import resolve_date_fields

_BUCKET_LABELS = {
    "overdue": "Overdue",
    "due_today": "Due today",
    "upcoming": "Upcoming",
}


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-tasks",
        description=(
            "Report open tasks carrying Obsidian Tasks dates (📅 due, ⏳ "
            "scheduled, 🛫 start), bucketed into overdue / due today / "
            "upcoming by their effective date. Read-only, no LLM."
        ),
    )
    p.add_argument(
        "--due-in",
        type=int,
        default=7,
        metavar="N",
        help="Upcoming horizon in days. Default: 7.",
    )
    p.add_argument(
        "--overdue",
        action="store_true",
        help="Report only overdue tasks (due before today).",
    )
    p.add_argument(
        "--group-by",
        choices=("due", "quest", "area"),
        default="due",
        help="Group output by urgency bucket (default), supported Quest, or Area.",
    )
    p.add_argument(
        "--date-field",
        action="append",
        choices=DATE_FIELDS,
        metavar="{due,scheduled,start}",
        help="Which Obsidian Tasks date drives bucketing. Repeatable; order "
        "sets precedence for tasks carrying several dates (first present "
        "wins). A field you omit is ignored entirely, so '--date-field "
        "scheduled' reports scheduled-dated tasks only. "
        "Default: workflows.tasks.date_fields from config, then due, "
        "scheduled, start.",
    )
    set_completer(
        p.add_argument(
            "--quest",
            default=None,
            help=(
                "Restrict to a single Quest (wikilink or bare name). A task "
                "matches when its note's 'supports:' includes that Quest."
            ),
        ),
        complete_quests,
    )
    p.add_argument(
        "--include-archive",
        action="store_true",
        help="Include notes under archive/ (excluded by default).",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    enable_completion(parser)
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        date_fields = resolve_date_fields(args.date_field, config.workflows)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        vault = find_vault(arg=args.vault, config=config)
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = scan_vault_tasks(
        vault,
        due_in=args.due_in,
        overdue_only=args.overdue,
        quest=args.quest,
        group_by=args.group_by,
        date_fields=date_fields,
        include_archive=args.include_archive,
    )

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_markdown(report))
    return 0


def _wikilink(path: str) -> str:
    return f"[[{PurePosixPath(path).stem}]]"


def _render_task(task: TaskItem, *, show_bucket: bool) -> str:
    parts = [f"{task.date_source} {task.effective_date}"]
    if show_bucket:
        parts.append(_BUCKET_LABELS[task.bucket].lower())
    return f"- {_wikilink(task.path)} {task.description} ({', '.join(parts)})"


def _grouped(report: TasksReport) -> list[tuple[str, list[TaskItem]]]:
    """Return ``(header, tasks)`` groups honoring ``report.group_by``.

    ``due`` groups by bucket in urgency order. ``quest`` / ``area`` group
    by the task's derived keys (a task with several keys appears under
    each); tasks with no keys fall under an "unassigned" group.
    """
    if report.group_by == "due":
        groups: list[tuple[str, list[TaskItem]]] = []
        for bucket in BUCKET_ORDER:
            tasks = [t for t in report.tasks if t.bucket == bucket]
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


def render_markdown(report: TasksReport) -> str:
    horizon = f"within {report.due_in} day(s)"
    if report.due_in == 0:
        horizon = "today or overdue"
    title = f"# Tasks as of {report.reference_date} ({horizon})"

    if not report.tasks:
        return f"{title}\n\nNo open tasks due.\n"

    show_bucket = report.group_by != "due"
    lines = [title, ""]
    for header, tasks in _grouped(report):
        lines.append(f"## {header} ({len(tasks)})")
        for task in tasks:
            lines.append(_render_task(task, show_bucket=show_bucket))
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

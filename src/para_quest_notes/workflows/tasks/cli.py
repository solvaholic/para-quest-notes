"""``pqn-tasks`` CLI entry point.

Read-only reporter: scans the vault for open tasks and prints dated tasks
by urgency plus optional unscheduled tasks. Text output is markdown
(plain ``-`` bullets, source note wikilinked) so a roundup can be pasted
into a daily note without re-parsing as live tasks; ``--format json``
emits the structured contract.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from para_quest_notes.adapter.cli import build_base_parser
from para_quest_notes.adapter.completion import (
    complete_quests,
    enable_completion,
    set_completer,
)
from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import ConfigError, VaultError
from para_quest_notes.adapter.vault import find_vault
from para_quest_notes.vault.scope import PARA_TYPES

from .contract import DATE_FIELDS, UNSCHEDULED_CHOICES
from .pipeline import scan_vault_tasks
from .render import render_markdown
from .settings import resolve_date_fields


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-tasks",
        description=(
            "Report dated open tasks by urgency and optionally tasks with no "
            "active Obsidian Tasks date (📅 due, ⏳ scheduled, 🛫 start). "
            "Read-only, no LLM."
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
        "--unscheduled",
        choices=UNSCHEDULED_CHOICES,
        default="hide",
        help=(
            "How to report tasks carrying none of the active date fields: "
            "'show' appends them after dated tasks; 'only' excludes all dated "
            "tasks. Omitted by default."
        ),
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
    p.add_argument(
        "--type",
        dest="types",
        action="append",
        choices=PARA_TYPES,
        help=(
            "Include only this PARA type. Repeatable and include-only: pass "
            "'--type area --type project' to include those and drop the rest, "
            "including untyped notes. Default: all types."
        ),
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
    if args.overdue and args.unscheduled == "only":
        parser.error("--overdue cannot be combined with --unscheduled only")

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
        types=args.types,
        quest=args.quest,
        group_by=args.group_by,
        date_fields=date_fields,
        include_archive=args.include_archive,
        unscheduled=args.unscheduled,
    )

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(render_markdown(report, unscheduled=args.unscheduled))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

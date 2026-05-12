"""``pqn-archive`` CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from para_quest_notes.adapter.cli import build_base_parser
from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import VaultError
from para_quest_notes.adapter.trace import TraceWriter, new_run_path
from para_quest_notes.adapter.vault import find_vault
from para_quest_notes.workflows.archive.contract import ArchiveInputs, ArchiveResult
from para_quest_notes.workflows.archive.pipeline import archive_note


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-archive",
        description="Archive a completed Project note: move it to archive/, "
        "cancel open tasks (opt-in), and record an Outcome.",
    )
    p.add_argument(
        "target",
        help="Vault-relative path to the Project, or just its basename (with or without .md).",
    )
    p.add_argument(
        "--outcome",
        default=None,
        help="Text for the '## Outcome' section. Required when the note doesn't already have one.",
    )
    p.add_argument(
        "--cancel-open-tasks",
        dest="cancel_open_tasks",
        action="store_true",
        help="Rewrite open ([ ]) and in-progress ([/]) tasks to cancelled "
        "([-]) with a '❌ <today>' marker. Without this flag, open tasks "
        "cause an escalation.",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write the archived file and delete the source. Without this flag, runs as a dry-run.",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = load_config(args.config)
    try:
        vault = find_vault(arg=args.vault, config=config)
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    inputs = ArchiveInputs(
        target=args.target,
        outcome=args.outcome,
        cancel_open_tasks=args.cancel_open_tasks,
    )

    trace_path = new_run_path(config.run_log_dir)
    with TraceWriter(trace_path) as trace:
        result = archive_note(
            inputs,
            vault=vault,
            apply=args.apply,
            config=config,
            trace=trace,
        )

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        _print_text(result, trace_path)

    if result.error or result.escalation:
        return 1
    return 0


def _print_text(result: ArchiveResult, trace_path: Path) -> None:
    mode = "APPLY" if result.apply else "DRY-RUN"
    print(f"pqn-archive [{mode}] vault={result.vault} run={result.run_id}")
    print(f"trace: {trace_path}")
    if result.escalation:
        print(f"  ESC step={result.escalation['step']}: {result.escalation['reason']}")
        return
    if result.error:
        print(f"  ERR {result.error}")
        return
    src = result.plan.source or "?"
    dest = result.plan.destination or "?"
    verb = "moved" if result.moved else "would move"
    print(f"  OK  {verb} {src} -> {dest}")
    if result.plan.tasks_cancelled:
        print(f"      cancelled {result.plan.tasks_cancelled} open task(s)")
    if result.plan.outcome_action != "none":
        print(f"      outcome: {result.plan.outcome_action}")
    if result.plan.frontmatter_migrated:
        print("      migrated tail backmatter -> frontmatter")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""``pqn-daily`` CLI entry point."""

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
from para_quest_notes.workflows.daily.contract import DailyInputs, DailyResult
from para_quest_notes.workflows.daily.pipeline import file_daily_note


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-daily",
        description="File a single YYYY-MM-DD.md note into "
        "resources/daily_notes/YYYY/MM/. Filing only; no authoring.",
    )
    p.add_argument(
        "target",
        help="Vault-relative path to the daily note, or just its basename "
        "(with or without .md). Basename search covers vault root, inbox/, "
        "and resources/daily_notes/.",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write the destination and remove the source. Without this flag, runs as a dry-run.",
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

    inputs = DailyInputs(target=args.target)

    trace_path = new_run_path(config.run_log_dir)
    with TraceWriter(trace_path) as trace:
        result = file_daily_note(
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


def _print_text(result: DailyResult, trace_path: Path) -> None:
    mode = "APPLY" if result.apply else "DRY-RUN"
    print(f"pqn-daily [{mode}] vault={result.vault} run={result.run_id}")
    print(f"trace: {trace_path}")
    if result.escalation:
        print(f"  ESC step={result.escalation['step']}: {result.escalation['reason']}")
        return
    if result.error:
        print(f"  ERR {result.error}")
        return
    src = result.plan.source or "?"
    dest = result.plan.destination or "?"
    if result.plan.already_at_destination:
        verb = "already at"
        print(f"  OK  {src} {verb} {dest}")
    else:
        verb = "moved" if result.moved else "would move"
        print(f"  OK  {verb} {src} -> {dest}")
    if result.plan.h1_inserted:
        print("      inserted # YYYY-MM-DD H1")
    if result.plan.frontmatter_migrated:
        print("      migrated tail backmatter -> frontmatter")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

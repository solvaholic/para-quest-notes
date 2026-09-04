"""``pqn-daily`` CLI entry point."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from para_quest_notes.adapter.cli import build_base_parser
from para_quest_notes.adapter.completion import (
    complete_daily_targets,
    enable_completion,
    set_completer,
)
from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import ConfigError, VaultError
from para_quest_notes.adapter.trace import TraceWriter, new_run_path
from para_quest_notes.adapter.vault import find_vault
from para_quest_notes.workflows.daily.contract import DailyInputs, DailyResult
from para_quest_notes.workflows.daily.pipeline import file_daily_note
from para_quest_notes.workflows.daily.settings import DailySettings, resolve_daily_settings


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-daily",
        description="Select, file, create, or open one YYYY-MM-DD.md daily note.",
    )
    set_completer(
        p.add_argument(
            "target",
            nargs="?",
            help="Vault-relative path to the daily note, or just its basename "
            "(with or without .md). Basename search covers vault root, inbox/, "
            "and resources/daily_notes/.",
        ),
        complete_daily_targets,
    )
    selection = p.add_mutually_exclusive_group()
    selection.add_argument(
        "--today",
        action="store_true",
        help="Select today's daily note. This is the default when target is omitted.",
    )
    selection.add_argument(
        "--date",
        type=_calendar_date,
        help="Select a daily note by YYYY-MM-DD calendar date.",
    )
    p.add_argument(
        "--create-missing",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Plan or create a missing selected date. Overrides workflows.daily.create_missing.",
    )
    p.add_argument(
        "--open",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Open the real file after success. Overrides workflows.daily.open_existing.",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write the destination and remove the source. Without this flag, runs as a dry-run.",
    )
    return p


def _calendar_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a real YYYY-MM-DD date") from exc
    if parsed.isoformat() != value:
        raise argparse.ArgumentTypeError(f"{value!r} is not a real YYYY-MM-DD date")
    return value


def main(argv: Sequence[str] | None = None, *, today: date | None = None) -> int:
    parser = build_parser()
    enable_completion(parser)
    args = parser.parse_args(argv)
    if args.target is not None and (args.today or args.date is not None):
        parser.error("target cannot be combined with --today or --date")

    try:
        config = load_config(args.config)
        settings = resolve_daily_settings(config.workflows)
        vault = find_vault(arg=args.vault, config=config)
    except (ConfigError, VaultError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    target = args.target or args.date or (today or date.today()).isoformat()
    create_missing = settings.create_missing if args.create_missing is None else args.create_missing
    should_open = settings.open_existing if args.open is None else args.open
    inputs = DailyInputs(target=target, create_missing=create_missing)

    trace_path = new_run_path(config.run_log_dir)
    with TraceWriter(trace_path) as trace:
        result = file_daily_note(
            inputs,
            vault=vault,
            apply=args.apply,
            config=config,
            trace=trace,
        )

    if should_open and result.ok:
        _open_note(result, vault=vault, settings=settings)

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        _print_text(result, trace_path)

    if result.error or result.escalation or result.open_error:
        return 1
    return 0


def _open_note(result: DailyResult, *, vault: Path, settings: DailySettings) -> None:
    relative_path = _real_note_path(result)
    if relative_path is None:
        return
    if settings.editor is None:
        result.ok = False
        result.open_error = (
            "opening requested but workflows.daily.editor is not configured "
            "(set it to a non-empty argv list)"
        )
        return

    absolute_path = vault / relative_path
    if not absolute_path.is_file():
        result.ok = False
        result.open_error = f"could not open missing note: {relative_path}"
        return

    argv = [*settings.editor, str(absolute_path)]
    try:
        subprocess.run(argv, check=True, shell=False)
    except FileNotFoundError:
        result.ok = False
        result.open_error = (
            f"editor executable not found: {settings.editor[0]!r} "
            "(configured by workflows.daily.editor)"
        )
        return
    except subprocess.CalledProcessError as exc:
        result.ok = False
        result.open_error = f"editor exited with exit code {exc.returncode}: {settings.editor[0]!r}"
        return

    result.opened = True
    result.open_path = relative_path


def _real_note_path(result: DailyResult) -> str | None:
    if result.plan.would_create and not result.created:
        return None
    if result.created or result.moved or result.plan.already_at_destination:
        return result.plan.destination
    return result.plan.source


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
    if result.plan.would_create:
        verb = "created" if result.created else "would create"
        print(f"  OK  {verb} {dest}")
    elif result.plan.already_at_destination:
        print(f"  OK  note already exists at {dest}")
    else:
        verb = "moved" if result.moved else "would move"
        print(f"  OK  {verb} {src} -> {dest}")
    if result.plan.h1_inserted:
        print("      inserted # YYYY-MM-DD H1")
    if result.plan.frontmatter_migrated:
        print("      migrated tail backmatter -> frontmatter")
    if result.opened:
        print(f"      opened {result.open_path}")
    elif result.open_error:
        print(f"  ERR could not open note: {result.open_error}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

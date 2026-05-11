"""``pqn-ingest`` CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from para_quest_notes.adapter.cli import add_llm_args, build_base_parser
from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import VaultError
from para_quest_notes.adapter.llm import OllamaClient
from para_quest_notes.adapter.trace import TraceWriter, new_run_path
from para_quest_notes.adapter.vault import find_vault
from para_quest_notes.workflows.ingest_inbox.contract import IngestResult
from para_quest_notes.workflows.ingest_inbox.pipeline import ingest_inbox


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-ingest",
        description="Triage notes from <vault>/inbox/ into PARA + Quest locations.",
    )
    add_llm_args(p)
    p.add_argument(
        "--apply",
        action="store_true",
        help="Apply moves and rewrites. Without this flag, runs as a dry-run.",
    )
    p.add_argument(
        "--file",
        type=Path,
        action="append",
        help="Process only this file (relative to the vault or absolute). Repeatable.",
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

    files = _resolve_files(vault, args.file) if args.file else None

    llm = OllamaClient(
        base_url=config.ollama.base_url,
        default_model=args.model or config.ollama.default_model,
        timeout_seconds=config.ollama.request_timeout_seconds,
    )

    trace_path = new_run_path(config.run_log_dir)
    with TraceWriter(trace_path) as trace:
        result = ingest_inbox(
            vault,
            llm=llm,
            apply=args.apply,
            model=args.model,
            config=config,
            trace=trace,
            files=files,
        )

    if args.format == "json":
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        _print_text(result, trace_path)

    # Exit nonzero if any file errored or escalated, so cron/agents notice.
    has_problems = any(not f.ok for f in result.files)
    return 1 if has_problems else 0


def _resolve_files(vault: Path, requested: list[Path]) -> list[Path]:
    out: list[Path] = []
    for f in requested:
        p = f if f.is_absolute() else vault / f
        if not p.exists():
            print(f"warning: skipping missing file: {p}", file=sys.stderr)
            continue
        out.append(p)
    return out


def _print_text(result: IngestResult, trace_path: Path) -> None:
    mode = "APPLY" if result.apply else "DRY-RUN"
    print(f"pqn-ingest [{mode}] vault={result.vault} run={result.run_id}")
    print(f"trace: {trace_path}")
    if not result.files:
        print("no inbox files found.")
        return
    for f in result.files:
        status = "OK " if f.ok else "ESC" if f.escalation else "ERR"
        dest = f.decisions.destination or "?"
        quests = ",".join(f.decisions.quests) if f.decisions.quests else "-"
        print(f"  [{status}] {f.source} -> {dest}  quests={quests}")
        if f.escalation:
            print(f"        escalate({f.escalation['step']}): {f.escalation['reason']}")
        elif f.error:
            print(f"        error: {f.error}")
        elif f.change and f.change.wikilinks_rewritten:
            n = sum(h["occurrences"] for h in f.change.wikilinks_rewritten)
            verb = "rewrote" if result.apply else "would rewrite"
            print(
                f"        {verb} {n} wikilink(s) across {len(f.change.wikilinks_rewritten)} file(s)"
            )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

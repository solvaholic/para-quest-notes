"""``pqn-create`` CLI entry point."""

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
from para_quest_notes.workflows.create.contract import CreateInputs, CreateResult
from para_quest_notes.workflows.create.path_inference import (
    InferredInputs,
    PathInferenceError,
    infer_from_path,
)
from para_quest_notes.workflows.create.pipeline import create_note


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-create",
        description="Create a single new note directly into its PARA + Quest home.",
    )
    p.add_argument(
        "path",
        nargs="?",
        default=None,
        help=(
            "Optional destination path. Infers --type, --title, --sub-path, "
            "and optionally --vault from the path structure. "
            "E.g. 'projects/sub/My Note.md' infers --type project "
            "--sub-path sub --title 'My Note'. Explicit flags override inferred values."
        ),
    )
    p.add_argument(
        "--type",
        default=None,
        choices=("project", "area", "resource"),
        help="PARA type for the new note.",
    )
    p.add_argument(
        "--title",
        default=None,
        help="Title Case name. Becomes the filename verbatim (with .md).",
    )
    p.add_argument(
        "--quest",
        choices=("main", "side", "none"),
        default="none",
        help="Quest type for the new note. Default: none.",
    )
    p.add_argument(
        "--supports",
        action="append",
        default=None,
        help=(
            "Wikilink to a Quest this note supports, e.g. '[[Health]]'. Repeatable. "
            "Optional for project and area notes: omit it to file into inbox/."
        ),
    )
    p.add_argument(
        "--sub-path",
        dest="sub_path",
        default=None,
        help="Sub-directory under the PARA top-level (e.g. '2026/' or 'Home/Water').",
    )
    p.add_argument(
        "--source-url",
        dest="source_url",
        default=None,
        help="Source URL for a Resource note (stored in frontmatter and surfaced in the body).",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Write the file. Without this flag, runs as a dry-run.",
    )
    return p


def _resolve_inputs(args: argparse.Namespace) -> tuple[CreateInputs, Path | None]:
    """Merge inferred values from positional path with explicit flags.

    Explicit flags always override inferred values. Returns the merged
    CreateInputs and an optional vault path hint from the path.
    """
    inferred = InferredInputs()
    vault_hint: Path | None = None

    if args.path is not None:
        inferred = infer_from_path(args.path)
        vault_hint = inferred.vault

    # Explicit flags override inferred values
    note_type = args.type if args.type is not None else inferred.type
    title = args.title if args.title is not None else inferred.title
    sub_path = args.sub_path if args.sub_path is not None else inferred.sub_path

    # Validate that we have the required values
    if note_type is None:
        print(
            "error: --type is required (or infer it from a positional path "
            "like 'projects/My Note.md')",
            file=sys.stderr,
        )
        raise SystemExit(2)
    if title is None:
        print(
            "error: --title is required (or infer it from a positional path "
            "like 'projects/My Note.md')",
            file=sys.stderr,
        )
        raise SystemExit(2)

    inputs = CreateInputs(
        title=title,
        type=note_type,
        quest=args.quest,
        supports=list(args.supports) if args.supports else None,
        sub_path=sub_path,
        source_url=args.source_url,
    )
    return inputs, vault_hint


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    config = load_config(args.config)

    try:
        inputs, vault_hint = _resolve_inputs(args)
    except PathInferenceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Vault resolution: explicit --vault > path-inferred vault > normal discovery
    vault_arg = args.vault
    if vault_arg is None and vault_hint is not None:
        vault_arg = vault_hint

    try:
        vault = find_vault(arg=vault_arg, config=config)
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    trace_path = new_run_path(config.run_log_dir)
    with TraceWriter(trace_path) as trace:
        result = create_note(
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


def _print_text(result: CreateResult, trace_path: Path) -> None:
    mode = "APPLY" if result.apply else "DRY-RUN"
    print(f"pqn-create [{mode}] vault={result.vault} run={result.run_id}")
    print(f"trace: {trace_path}")
    if result.escalation:
        print(f"  ESC step={result.escalation['step']}: {result.escalation['reason']}")
        return
    if result.error:
        print(f"  ERR {result.error}")
        return
    dest = result.plan.destination or "?"
    verb = "wrote" if result.written else "would write"
    print(f"  OK  {verb} {dest}")
    if result.plan.frontmatter:
        keys = ", ".join(result.plan.frontmatter.keys())
        print(f"      frontmatter keys: {keys}")
    for note in result.plan.notes:
        print(f"      note: {note}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

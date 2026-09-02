"""``pqn-validate`` CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from para_quest_notes.adapter.cli import build_base_parser
from para_quest_notes.adapter.completion import enable_completion
from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import VaultError
from para_quest_notes.adapter.vault import find_vault

from .api import validate_paths, validate_vault
from .checks import CHECKS_BY_ID
from .contract import ValidateReport
from .fix import FixReport, fix_vault

_SEVERITY_CHOICES = ("error", "warning", "info")


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-validate",
        description=(
            "Audit a vault for duplicate filenames and malformed YAML front/backmatter. Read-only."
        ),
    )
    p.add_argument(
        "--path",
        type=Path,
        action="append",
        help=(
            "Restrict reporting to this path (relative to the vault or "
            "absolute). Repeatable. Vault-wide context (e.g. filename "
            "collision detection) still considers the whole vault."
        ),
    )
    p.add_argument(
        "--check",
        action="append",
        choices=sorted(CHECKS_BY_ID),
        help="Run only this check. Repeatable. Default: run all.",
    )
    p.add_argument(
        "--severity",
        choices=_SEVERITY_CHOICES,
        default="warning",
        help="Minimum severity to report. Default: warning.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors when computing the exit code.",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help=(
            "Migrate legacy 'quest:' frontmatter keys to canonical 'quest-kind:'. "
            "Dry-run unless combined with --apply. Ignores other --check selections."
        ),
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="With --fix, write changes to disk. Without it, --fix is a dry-run.",
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

    config = load_config(args.config)
    try:
        vault = find_vault(arg=args.vault, config=config)
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.fix:
        fix_report = fix_vault(
            vault,
            paths=args.path,
            include_archive=args.include_archive,
            apply=args.apply,
        )
        if args.format == "json":
            print(json.dumps(fix_report.to_dict(), indent=2))
        else:
            _print_fix_text(fix_report)
        # A skip means a note we refused to guess about — surface it as an error.
        return 1 if fix_report.skipped else 0

    if args.path:
        report = validate_paths(
            vault,
            args.path,
            checks=args.check,
            min_severity=args.severity,
            include_archive=args.include_archive,
        )
    else:
        report = validate_vault(
            vault,
            checks=args.check,
            min_severity=args.severity,
            include_archive=args.include_archive,
        )

    if args.format == "json":
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_text(report)

    has_errors = bool(report.errors)
    has_warnings = bool(report.warnings)
    if has_errors or (args.strict and has_warnings):
        return 1
    return 0


def _print_text(report: ValidateReport) -> None:
    print(f"pqn-validate vault={report.vault} files_scanned={report.files_scanned}")
    print(f"checks: {', '.join(report.checks_run)}")
    if not report.issues:
        print("no issues found.")
        return
    print(
        f"issues: {len(report.issues)} "
        f"(errors={len(report.errors)}, warnings={len(report.warnings)})"
    )
    for i in report.issues:
        loc = f"{i.path}:{i.line}" if i.line is not None else i.path
        print(f"  [{i.severity:7}] {i.check:24} {loc}  {i.message}")
        if i.related:
            for r in i.related:
                print(f"               related: {r}")


def _print_fix_text(report: FixReport) -> None:
    mode = "apply" if report.applied else "dry-run"
    print(f"pqn-validate --fix vault={report.vault} mode={mode}")
    if not report.entries:
        print("no legacy 'quest:' keys found.")
        return
    verb = "migrated" if report.applied else "would migrate"
    print(f"{verb}: {len(report.migrated)}, skipped: {len(report.skipped)}")
    for e in report.migrated:
        print(f"  [{verb}] {e.path}  quest: {e.value!r} -> quest-kind")
    for e in report.skipped:
        print(f"  [skipped] {e.path}  {e.reason}")
    if not report.applied and report.migrated:
        print("re-run with --apply to write these changes.")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

"""``python -m para_quest_notes.corpus`` entry point.

Phase 2 doesn't ship a ``pqn-corpus`` console script (see
``docs/PLAN.md`` Phase 2 decisions); this module is the stable
invocation path for now.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from para_quest_notes.corpus.generate import (
    DEFAULT_COUNTS,
    GenerateOptions,
    generate_vault,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m para_quest_notes.corpus",
        description="Generate a synthetic PARA + Quest sample vault.",
    )
    p.add_argument("--out", required=True, type=Path, help="output vault directory")
    p.add_argument("--seed", type=int, default=0, help="RNG seed (default: 0)")
    p.add_argument(
        "--projects",
        type=int,
        default=DEFAULT_COUNTS["projects"],
        help=f"number of project notes (default: {DEFAULT_COUNTS['projects']})",
    )
    p.add_argument(
        "--areas",
        type=int,
        default=DEFAULT_COUNTS["areas"],
        help="number of area notes (0 = every Area in seeds.yaml)",
    )
    p.add_argument(
        "--resources",
        type=int,
        default=DEFAULT_COUNTS["resources"],
        help="number of resource notes (0 = every Resource in seeds.yaml)",
    )
    p.add_argument(
        "--inbox",
        type=int,
        default=DEFAULT_COUNTS["inbox"],
        help=f"number of inbox notes (default: {DEFAULT_COUNTS['inbox']})",
    )
    p.add_argument(
        "--daily",
        type=int,
        default=DEFAULT_COUNTS["daily"],
        help=f"number of consecutive daily notes (default: {DEFAULT_COUNTS['daily']})",
    )
    p.add_argument(
        "--quirk-rate",
        type=float,
        default=0.3,
        help="probability of each quirk per note (default: 0.3)",
    )
    p.add_argument(
        "--clean",
        action="store_true",
        help="wipe --out if it exists and is non-empty",
    )
    p.add_argument(
        "--no-manifest",
        dest="write_manifest",
        action="store_false",
        help="skip writing _corpus_manifest.json",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    options = GenerateOptions(
        seed=args.seed,
        projects=args.projects,
        areas=args.areas,
        resources=args.resources,
        inbox=args.inbox,
        daily=args.daily,
        quirk_rate=args.quirk_rate,
        write_manifest=args.write_manifest,
        clean=args.clean,
    )
    try:
        result = generate_vault(args.out, options)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"wrote {len(result.files)} notes to {result.out}")
    if options.write_manifest:
        print(f"manifest: {result.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

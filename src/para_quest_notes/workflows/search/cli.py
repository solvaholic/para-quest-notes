"""``pqn-search`` CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from para_quest_notes.adapter.cli import build_base_parser
from para_quest_notes.adapter.config import load_config
from para_quest_notes.adapter.errors import VaultError
from para_quest_notes.adapter.vault import find_vault

from .api import render_text, search

_TYPE_CHOICES = ("project", "area", "resource")


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-search",
        description=(
            "Search the vault for notes by title and/or body keywords, scoped "
            "and ranked by the PARA + Quest model. Read-only, no LLM."
        ),
    )
    p.add_argument(
        "query",
        nargs="+",
        help=(
            "Keyword(s) to match (case-insensitive). A note matches only when "
            "all keywords are present in the searched fields."
        ),
    )
    p.add_argument(
        "--title",
        action="store_true",
        help="Match the note title (basename). Default: title and content.",
    )
    p.add_argument(
        "--content",
        action="store_true",
        help=(
            "Match the note body, including fenced code blocks. Default: title "
            "and content. (Passing both --title and --content is the same as "
            "passing neither.)"
        ),
    )
    p.add_argument(
        "--type",
        dest="types",
        action="append",
        choices=_TYPE_CHOICES,
        help=(
            "Include only this PARA type. Repeatable and include-only: pass "
            "'--type area --type project' to include those and drop the rest. "
            "Default: all types."
        ),
    )
    p.add_argument(
        "--quest",
        default=None,
        help=("Restrict to notes whose 'supports:' includes this Quest (wikilink or bare name)."),
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of results. Default: unlimited.",
    )
    p.add_argument(
        "--include-archive",
        action="store_true",
        help="Include notes under archive/ (excluded by default).",
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

    results = search(
        vault,
        args.query,
        title=args.title,
        content=args.content,
        types=args.types,
        quest=args.quest,
        include_archive=args.include_archive,
        limit=args.limit,
    )

    if args.format == "json":
        print(json.dumps(results.to_dict(), indent=2))
    else:
        print(render_text(results), end="")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

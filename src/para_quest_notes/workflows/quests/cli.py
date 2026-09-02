"""``pqn-quests`` CLI entry point."""

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
from para_quest_notes.adapter.errors import VaultError
from para_quest_notes.adapter.vault import find_vault

from .api import build_quest_index, render_markdown

_TYPE_CHOICES = ("project", "area", "resource")


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-quests",
        description=(
            "Generate the Main Quest index from the vault: group notes by the "
            "Quest(s) they support and emit the rollup. Read-only, no LLM."
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
            "Omitting a type excludes it (excluding 'area' also drops the "
            "Capabilities section). Default: all types."
        ),
    )
    set_completer(
        p.add_argument(
            "--quest",
            default=None,
            help=(
                "Restrict to a single Quest (wikilink or bare name). A note matches "
                "when its 'supports:' includes that Quest. Omits Capabilities and "
                "Unassigned."
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

    config = load_config(args.config)
    try:
        vault = find_vault(arg=args.vault, config=config)
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    index = build_quest_index(
        vault,
        types=args.types,
        quest=args.quest,
        include_archive=args.include_archive,
    )

    if args.format == "json":
        print(json.dumps(index.to_dict(), indent=2))
    else:
        # `text` is the redirectable markdown index (pqn-quests > index.md).
        print(render_markdown(index), end="")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

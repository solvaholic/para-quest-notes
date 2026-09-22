"""``pqn-search`` CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from para_quest_notes.adapter.cli import build_base_parser
from para_quest_notes.adapter.completion import (
    complete_link_targets,
    complete_quests,
    enable_completion,
    set_completer,
)
from para_quest_notes.adapter.config import Config, load_config
from para_quest_notes.adapter.errors import VaultError
from para_quest_notes.adapter.vault import find_vault

from .api import LinkTargetError, render_link_text, render_text, search, search_links
from .builder import DEFAULT_SNIPPET_RADIUS

_TYPE_CHOICES = ("project", "area", "resource")


def _non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return value


def build_parser() -> argparse.ArgumentParser:
    p = build_base_parser(
        prog="pqn-search",
        description=(
            "Search the vault by title/body keywords or direct outgoing links "
            "and backlinks, scoped by the PARA + Quest model. Read-only, no LLM."
        ),
    )
    p.add_argument(
        "query",
        nargs="*",
        help=(
            "Keyword(s) to match (case-insensitive). A note matches only when "
            "all keywords are present in the searched fields. Mutually "
            "exclusive with --links."
        ),
    )
    set_completer(
        p.add_argument(
            "--links",
            default=None,
            metavar="TARGET",
            help=(
                "Resolve one note and report its direct outgoing links and "
                "incoming backlinks. Accepts a unique basename or an exact "
                "vault-relative .md path."
            ),
        ),
        complete_link_targets,
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
    set_completer(
        p.add_argument(
            "--quest",
            default=None,
            help=(
                "Restrict to notes whose 'supports:' includes this Quest (wikilink or bare name)."
            ),
        ),
        complete_quests,
    )
    p.add_argument(
        "--limit",
        type=_non_negative_int,
        default=None,
        help="Cap the number of results. Default: unlimited.",
    )
    p.add_argument(
        "--snippet-radius",
        type=_non_negative_int,
        default=None,
        metavar="N",
        help=(
            "Characters of context to show on each side of a body match "
            "(also gates the title snippet). 0 suppresses snippets. Overrides "
            "the 'search.snippet_radius' config value. Default: "
            f"{DEFAULT_SNIPPET_RADIUS}."
        ),
    )
    p.add_argument(
        "--include-archive",
        action="store_true",
        help="Include notes under archive/ (excluded by default).",
    )
    return p


def _validate_mode(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    has_query = bool(args.query)
    has_links = args.links is not None
    if has_query and has_links:
        parser.error("positional query terms cannot be combined with --links")
    if not has_query and not has_links:
        parser.error("exactly one search mode is required: query terms or --links TARGET")
    if has_links and (args.title or args.content or args.snippet_radius is not None):
        parser.error("--title, --content, and --snippet-radius are keyword mode options")


def _resolve_snippet_radius(cli_value: int | None, config: Config) -> int:
    """Resolve the snippet radius: flag > config > default.

    Reads ``search.snippet_radius`` from the per-workflow config when the flag
    is omitted. A bad config value (non-int or negative) is a ``ValueError``
    so the caller can fail loudly, matching the config loader's "loud on shape
    mistakes" stance.
    """
    if cli_value is not None:
        return cli_value
    search_cfg = config.workflows.get("search") or {}
    raw = search_cfg.get("snippet_radius")
    if raw is None:
        return DEFAULT_SNIPPET_RADIUS
    value = int(raw)
    if value < 0:
        raise ValueError("search.snippet_radius must be >= 0")
    return value


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    enable_completion(parser)
    args = parser.parse_args(argv)
    _validate_mode(parser, args)

    config = load_config(args.config)
    try:
        vault = find_vault(arg=args.vault, config=config)
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.links is not None:
        try:
            link_results = search_links(
                vault,
                args.links,
                types=args.types,
                quest=args.quest,
                include_archive=args.include_archive,
                limit=args.limit,
            )
        except LinkTargetError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        rendered = (
            json.dumps(link_results.to_dict(), indent=2)
            if args.format == "json"
            else render_link_text(link_results)
        )
    else:
        try:
            snippet_radius = _resolve_snippet_radius(args.snippet_radius, config)
        except (TypeError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        keyword_results = search(
            vault,
            args.query,
            title=args.title,
            content=args.content,
            types=args.types,
            quest=args.quest,
            include_archive=args.include_archive,
            limit=args.limit,
            snippet_radius=snippet_radius,
        )
        rendered = (
            json.dumps(keyword_results.to_dict(), indent=2)
            if args.format == "json"
            else render_text(keyword_results)
        )

    print(rendered, end="\n" if args.format == "json" else "")

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

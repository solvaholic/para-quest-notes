"""Shared CLI plumbing for ``pqn-*`` entry points.

Every workflow CLI extends this base parser so flag names and semantics stay
consistent across ``pqn-ingest``, ``pqn-validate``, and the workflows still
to come. Workflow-specific flags are added by each workflow's ``cli.py``.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from para_quest_notes import __version__


def build_base_parser(
    *,
    prog: str,
    description: str,
) -> argparse.ArgumentParser:
    """Return an ``ArgumentParser`` with the flags every workflow shares.

    Shared flags:
        ``--vault PATH``    Path to the vault. Falls back to env / cwd
                            discovery when omitted.
        ``--config PATH``   Path to ``config.yaml``. Falls back to the XDG
                            default when omitted.
        ``--format``        Output format, ``json`` or ``text``. Default
                            ``text``.
        ``--version``       Print the installed version and exit.
    """
    parser = argparse.ArgumentParser(prog=prog, description=description)
    add_version_arg(parser)
    parser.add_argument(
        "--vault",
        type=Path,
        default=None,
        help="Path to the vault.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (overrides the XDG default).",
    )
    parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="text",
        help="Output format. Default: text.",
    )
    return parser


def add_version_arg(parser: argparse.ArgumentParser) -> None:
    """Add ``--version`` to ``parser``.

    Exposed separately from :func:`build_base_parser` so entry points that
    build their own parser (like ``pqn-eval``) report the same version
    string in the same format.
    """
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Print the installed version and exit.",
    )


def add_llm_args(parser: argparse.ArgumentParser) -> None:
    """Add LLM-related flags to ``parser``.

    Kept separate from :func:`build_base_parser` so no-LLM workflows (like
    ``pqn-validate``) don't advertise a flag they would silently ignore.
    """
    parser.add_argument(
        "--model",
        default=None,
        help="Override the default Ollama model for this run.",
    )

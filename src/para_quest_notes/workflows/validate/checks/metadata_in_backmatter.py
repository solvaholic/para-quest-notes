"""Warn when canonical PARA + Quest keys live in tail backmatter.

Frontmatter is canonical (see ``docs/PLAN.md`` "Open questions —
decided 2026-05-12"). Backmatter is tolerated on read and migrated on
touch by write-path workflows, but until that happens it is invisible
to tools that only look at frontmatter (Obsidian Properties, Dataview,
SSGs) — and, historically, to ``pqn-ingest``'s Quest discovery.

This check surfaces the friction so users can fix it (or know why
their notes will be rewritten on first touch).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from para_quest_notes.vault.frontmatter import CANONICAL_KEY_ORDER

from .._blocks import extract_blocks
from ..contract import ValidateIssue
from .frontmatter_yaml import _is_template

ID = "metadata_in_backmatter"

_CANONICAL_KEYS = frozenset(CANONICAL_KEY_ORDER)


def run(
    vault: Path,
    files: list[Path],
    all_md: list[Path],  # noqa: ARG001 — uniform check signature
) -> list[ValidateIssue]:
    issues: list[ValidateIssue] = []
    for path in files:
        if _is_template(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # frontmatter_yaml reports read errors; don't double-flag.
            continue
        blocks = extract_blocks(text)
        if blocks.backmatter is None:
            continue
        try:
            loaded = yaml.safe_load(blocks.backmatter.text)
        except yaml.YAMLError:
            # backmatter_yaml reports parse errors; don't double-flag.
            continue
        if not isinstance(loaded, dict):
            continue
        offenders = sorted(k for k in loaded if k in _CANONICAL_KEYS)
        if not offenders:
            continue
        issues.append(
            ValidateIssue(
                check=ID,
                severity="warning",
                path=path.relative_to(vault).as_posix(),
                message=(
                    f"canonical key(s) {offenders} in tail backmatter; "
                    "move to frontmatter (write-path workflows will migrate "
                    "this automatically on next touch)"
                ),
                line=blocks.backmatter.start_line,
                detail={"keys": offenders},
            )
        )
    return issues

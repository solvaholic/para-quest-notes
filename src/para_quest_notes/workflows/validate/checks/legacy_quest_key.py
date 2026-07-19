"""Warn when a note carries the legacy ``quest:`` classifier in frontmatter.

The Quest classifier field was renamed ``quest:`` -> ``quest-kind:`` in
issue #98. The legacy spelling is tolerated on read (with a warning) and
migrated to canonical on any write, but static notes the write-path
workflows never touch keep the legacy key indefinitely. This check
surfaces them so ``pqn-validate --fix`` can batch-migrate.

Scope is *frontmatter only*. A legacy ``quest:`` in tail backmatter is
already reported by ``metadata_in_backmatter`` (it flags the legacy key
alongside the canonical ones), so flagging it here too would double-count.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from para_quest_notes.vault.frontmatter import LEGACY_QUEST_KEY, QUEST_KIND_KEY

from .._blocks import extract_blocks
from ..contract import ValidateIssue
from .frontmatter_yaml import _is_template

ID = "legacy_quest_key"


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
        if blocks.frontmatter is None:
            continue
        try:
            loaded = yaml.safe_load(blocks.frontmatter.text)
        except yaml.YAMLError:
            # frontmatter_yaml reports parse errors; don't double-flag.
            continue
        if not isinstance(loaded, dict) or LEGACY_QUEST_KEY not in loaded:
            continue
        issues.append(
            ValidateIssue(
                check=ID,
                severity="warning",
                path=path.relative_to(vault).as_posix(),
                message=(
                    f"legacy '{LEGACY_QUEST_KEY}:' classifier key in frontmatter; "
                    f"rename to '{QUEST_KIND_KEY}:' (run `pqn-validate --fix`)"
                ),
                line=blocks.frontmatter.start_line,
                detail={"value": loaded[LEGACY_QUEST_KEY]},
            )
        )
    return issues

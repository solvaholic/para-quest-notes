"""Validate that the optional YAML backmatter block parses cleanly.

Backmatter is the ``---...---`` fence at the **bottom** of a note (used
in ``solvaholic/at-home`` for archive Outcome statements). It is
optional; absence is not an issue.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .._blocks import extract_blocks
from ..contract import ValidateIssue
from .frontmatter_yaml import _is_template, _short, _yaml_error_line

ID = "backmatter_yaml"


def run(
    vault: Path,
    files: list[Path],
    all_md: list[Path],  # noqa: ARG001
) -> list[ValidateIssue]:
    issues: list[ValidateIssue] = []
    for path in files:
        if _is_template(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # frontmatter_yaml will report the read error; don't double-flag.
            continue
        blocks = extract_blocks(text)
        if blocks.backmatter is None:
            continue
        try:
            loaded = yaml.safe_load(blocks.backmatter.text)
        except yaml.YAMLError as exc:
            issues.append(
                ValidateIssue(
                    check=ID,
                    severity="error",
                    path=path.relative_to(vault).as_posix(),
                    message=f"invalid YAML in backmatter: {_short(exc)}",
                    line=_yaml_error_line(exc, blocks.backmatter.start_line),
                )
            )
            continue
        if loaded is not None and not isinstance(loaded, dict):
            issues.append(
                ValidateIssue(
                    check=ID,
                    severity="error",
                    path=path.relative_to(vault).as_posix(),
                    message=(f"backmatter must parse to a mapping, got {type(loaded).__name__}"),
                    line=blocks.backmatter.start_line,
                )
            )
    return issues

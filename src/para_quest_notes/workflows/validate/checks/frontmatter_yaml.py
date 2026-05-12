"""Validate that the YAML frontmatter block parses cleanly."""

from __future__ import annotations

from pathlib import Path

import yaml

from .._blocks import extract_blocks
from ..contract import ValidateIssue

ID = "frontmatter_yaml"


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
        except (OSError, UnicodeDecodeError) as exc:
            issues.append(
                ValidateIssue(
                    check=ID,
                    severity="error",
                    path=path.relative_to(vault).as_posix(),
                    message=f"could not read file: {exc}",
                )
            )
            continue
        blocks = extract_blocks(text)

        if blocks.frontmatter_unterminated:
            issues.append(
                ValidateIssue(
                    check=ID,
                    severity="error",
                    path=path.relative_to(vault).as_posix(),
                    message="frontmatter opened with '---' but no closing '---' found",
                    line=1,
                )
            )
            continue

        if blocks.frontmatter is None:
            continue

        try:
            loaded = yaml.safe_load(blocks.frontmatter.text)
        except yaml.YAMLError as exc:
            line = _yaml_error_line(exc, blocks.frontmatter.start_line)
            issues.append(
                ValidateIssue(
                    check=ID,
                    severity="error",
                    path=path.relative_to(vault).as_posix(),
                    message=f"invalid YAML in frontmatter: {_short(exc)}",
                    line=line,
                )
            )
            continue

        if loaded is not None and not isinstance(loaded, dict):
            issues.append(
                ValidateIssue(
                    check=ID,
                    severity="error",
                    path=path.relative_to(vault).as_posix(),
                    message=(f"frontmatter must parse to a mapping, got {type(loaded).__name__}"),
                    line=blocks.frontmatter.start_line,
                )
            )
    return issues


def _is_template(path: Path) -> bool:
    return any(part.lower() == "templates" for part in path.parts)


def _yaml_error_line(exc: yaml.YAMLError, base_line: int) -> int | None:
    mark = getattr(exc, "problem_mark", None)
    if mark is None:
        return None
    # YAML marks are 0-based and relative to the YAML text we passed in
    # (which started one line *below* the opening ``---``). So absolute
    # line = base_line (the ``---``) + mark.line + 1.
    return int(base_line) + int(mark.line) + 1


def _short(exc: yaml.YAMLError) -> str:
    msg = str(exc).splitlines()[0]
    return msg if len(msg) <= 120 else msg[:117] + "..."

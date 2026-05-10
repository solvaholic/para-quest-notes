"""YAML frontmatter parser/serializer for markdown notes.

A note may begin with a YAML block delimited by ``---`` lines. Anything
before the opening ``---`` (allowing only blank lines) means the note has
no frontmatter — we don't try to insert one in a weird place.

We keep the exact body string (everything after the closing ``---``) so
round-tripping doesn't churn whitespace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import yaml

DELIM = "---"


@dataclass
class ParsedNote:
    """Parsed frontmatter + body of a markdown note."""

    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    had_frontmatter: bool = False

    def render(self) -> str:
        """Render back to a string. Always emits frontmatter if non-empty."""
        if not self.frontmatter:
            return self.body
        dumped = yaml.safe_dump(
            self.frontmatter,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
        ).rstrip("\n")
        return f"{DELIM}\n{dumped}\n{DELIM}\n{self.body}"


def parse(text: str) -> ParsedNote:
    """Parse a markdown string into frontmatter + body.

    No frontmatter? Returns the whole string as ``body`` and
    ``had_frontmatter=False``.
    """
    if not text.startswith(DELIM):
        return ParsedNote(body=text)

    # Allow the leading delim line to end with \n or \r\n.
    rest = text[len(DELIM) :]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    else:
        # Not actually a delimiter line (e.g. ``---foo``).
        return ParsedNote(body=text)

    end_idx = _find_closing_delim(rest)
    if end_idx is None:
        return ParsedNote(body=text)

    fm_text = rest[:end_idx]
    after = rest[end_idx:]
    # Strip the closing delim line.
    after = after[len(DELIM) :]
    if after.startswith("\r\n"):
        after = after[2:]
    elif after.startswith("\n"):
        after = after[1:]

    try:
        loaded = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError:
        # Malformed YAML — treat the whole file as body so the user can fix it.
        return ParsedNote(body=text)

    if not isinstance(loaded, dict):
        return ParsedNote(body=text)

    return ParsedNote(frontmatter=loaded, body=after, had_frontmatter=True)


def _find_closing_delim(text: str) -> int | None:
    """Find the start index of the closing ``---`` delimiter line."""
    idx = 0
    while idx < len(text):
        nl = text.find("\n", idx)
        line_end = nl if nl != -1 else len(text)
        line = text[idx:line_end].rstrip("\r")
        if line == DELIM:
            return idx
        if nl == -1:
            return None
        idx = nl + 1
    return None


def merge(existing: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Apply ``updates`` over ``existing`` preserving key order where possible.

    Updated keys keep their original position; new keys are appended.
    """
    merged: dict[str, Any] = {}
    for k, v in existing.items():
        merged[k] = updates.get(k, v)
    for k, v in updates.items():
        if k not in merged:
            merged[k] = v
    return merged

"""YAML frontmatter parser/serializer for markdown notes.

A note may begin with a YAML block delimited by ``---`` lines. Anything
before the opening ``---`` (allowing only blank lines) means the note has
no frontmatter — we don't try to insert one in a weird place.

We keep the exact body string (everything after the closing ``---``) so
round-tripping doesn't churn whitespace.

This module is also the single source of truth for *canonical* frontmatter
shape used by write-path workflows (``pqn-create``, ``pqn-ingest --apply``,
and eventually ``pqn-archive``). See :func:`canonical_frontmatter` and
:func:`dump_frontmatter`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml

DELIM = "---"

# Canonical key order for the PARA + Quest schema. Keys outside this set
# (legacy keys, user-added keys) follow in their original order. Driven by
# docs/notes-system.md "Metadata schema (frontmatter)".
CANONICAL_KEY_ORDER: tuple[str, ...] = (
    "type",
    "quest",
    "supports",
    "source_url",
    "created",
)


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


def canonical_frontmatter(
    data: dict[str, Any],
    *,
    key_order: Sequence[str] = CANONICAL_KEY_ORDER,
) -> dict[str, Any]:
    """Reorder and prune ``data`` into canonical PARA + Quest shape.

    - Keys in ``key_order`` come first, in that order, when present.
    - Other keys follow in their original insertion order.
    - Keys with value ``None`` are dropped.
    - ``supports`` is dropped when empty (``[]`` or ``None``); the spec
      says omit the key rather than emit ``supports: []``.

    Doesn't validate values — schema enforcement is the workflow's job.
    """
    out: dict[str, Any] = {}
    for key in key_order:
        if key not in data:
            continue
        value = data[key]
        if value is None:
            continue
        if key == "supports" and not value:
            continue
        out[key] = value
    for key, value in data.items():
        if key in key_order or key in out:
            continue
        if value is None:
            continue
        out[key] = value
    return out


def dump_frontmatter(
    data: dict[str, Any],
    *,
    key_order: Sequence[str] = CANONICAL_KEY_ORDER,
) -> str:
    """Render ``data`` as a canonical ``---...---`` frontmatter block.

    Returns a string that ends with a newline. Empty input renders as the
    empty string (no block at all) — callers compose their own body.

    Wikilink strings (``[[Foo]]``) are emitted quoted because ``[`` opens
    a YAML flow sequence; PyYAML handles this for us when scalars contain
    flow indicators, but we double-check via the existing ``ParsedNote``
    rendering path so the two stay in lockstep.
    """
    canon = canonical_frontmatter(data, key_order=key_order)
    if not canon:
        return ""
    return ParsedNote(frontmatter=canon, body="", had_frontmatter=True).render()


@dataclass
class SplitNote:
    """A note split into frontmatter + body + (optional) tail backmatter.

    Backmatter is the deprecated trailing ``---...---`` block some legacy
    notes still carry. Write-path workflows migrate it into frontmatter
    on touch (see ``docs/PLAN.md`` "Open questions — decided 2026-05-12").

    ``body`` excludes both fences. ``trailing_whitespace`` preserves any
    whitespace that appeared after the backmatter so round-tripping
    doesn't churn the file's tail.
    """

    frontmatter: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    backmatter: dict[str, Any] = field(default_factory=dict)
    had_frontmatter: bool = False
    had_backmatter: bool = False
    trailing_whitespace: str = ""


def split_note(text: str) -> SplitNote:
    """Parse a note into frontmatter + body + (optional) backmatter.

    Tolerates malformed backmatter the same way :func:`parse` tolerates
    malformed frontmatter: if the trailing fence isn't a valid YAML
    mapping, we leave it in the body untouched.
    """
    parsed = parse(text)
    body = parsed.body
    split = SplitNote(
        frontmatter=parsed.frontmatter,
        body=body,
        had_frontmatter=parsed.had_frontmatter,
    )

    # Find the trailing ``---`` line, ignoring blank trailing lines.
    trailing_ws_len = len(body) - len(body.rstrip())
    trailing_ws = body[len(body) - trailing_ws_len :] if trailing_ws_len else ""
    body_stripped = body.rstrip()
    if not body_stripped.endswith(DELIM):
        return split

    # Walk lines from the end to find the closing fence and opener.
    lines = body_stripped.splitlines()
    if not lines or lines[-1] != DELIM:
        return split
    close_idx = len(lines) - 1
    open_idx: int | None = None
    for i in range(close_idx - 1, -1, -1):
        if lines[i] == DELIM:
            open_idx = i
            break
    # Need at least one line between open and close (`---\n---` isn't BM).
    if open_idx is None or open_idx >= close_idx - 1:
        return split

    bm_text = "\n".join(lines[open_idx + 1 : close_idx])
    try:
        loaded = yaml.safe_load(bm_text) or {}
    except yaml.YAMLError:
        return split
    if not isinstance(loaded, dict):
        return split

    pre_body = "\n".join(lines[:open_idx])
    if open_idx > 0:
        pre_body += "\n"
    split.body = pre_body
    split.backmatter = loaded
    split.had_backmatter = True
    split.trailing_whitespace = trailing_ws
    return split

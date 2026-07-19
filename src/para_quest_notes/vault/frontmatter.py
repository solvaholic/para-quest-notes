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

import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import yaml

DELIM = "---"

# The Quest classifier frontmatter field. ``quest-kind:`` is canonical; the
# legacy ``quest:`` spelling is tolerated on read (with a warning) and migrated
# to ``quest-kind:`` on any write. See issue #98 and docs/notes-system.md.
QUEST_KIND_KEY = "quest-kind"
LEGACY_QUEST_KEY = "quest"

# Canonical key order for the PARA + Quest schema. Keys outside this set
# (legacy keys, user-added keys) follow in their original order. Driven by
# docs/notes-system.md "Metadata schema (frontmatter)".
CANONICAL_KEY_ORDER: tuple[str, ...] = (
    "type",
    QUEST_KIND_KEY,
    "supports",
    "source_url",
    "created",
)


class LegacyQuestKeyWarning(UserWarning):
    """Emitted when a legacy ``quest:`` classifier key is read or supplied.

    Distinct category so callers (and tests) can filter or assert on it via
    :func:`warnings.catch_warnings` / :func:`pytest.warns`.
    """


def read_quest_kind(meta: dict[str, Any]) -> tuple[Any, bool]:
    """Read the Quest classifier from ``meta``, tolerating the legacy key.

    Returns ``(value, used_legacy)``. Prefers canonical ``quest-kind:``; falls
    back to legacy ``quest:`` when only that is present. ``used_legacy`` is True
    only when the value came from the legacy key, so callers can warn once.
    Returns ``(None, False)`` when neither key is present.
    """
    if QUEST_KIND_KEY in meta:
        return meta.get(QUEST_KIND_KEY), False
    if LEGACY_QUEST_KEY in meta:
        return meta.get(LEGACY_QUEST_KEY), True
    return None, False


def warn_legacy_quest_key(path: object | None = None) -> None:
    """Emit a :class:`LegacyQuestKeyWarning` naming ``path`` when available."""
    where = f" in {path}" if path is not None else ""
    warnings.warn(
        f"legacy 'quest:' classifier key found{where}; rename it to "
        f"'{QUEST_KIND_KEY}:' (write-path workflows migrate this on touch)",
        LegacyQuestKeyWarning,
        stacklevel=2,
    )


def migrate_quest_kind(data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Rename a legacy ``quest:`` key to ``quest-kind:`` preserving order.

    Returns ``(new_data, had_legacy)``. When both keys are present the
    canonical ``quest-kind:`` value wins and the legacy key is dropped. When
    no legacy key is present, ``data`` is returned unchanged.
    """
    if LEGACY_QUEST_KEY not in data:
        return data, False
    out: dict[str, Any] = {}
    for key, value in data.items():
        if key == LEGACY_QUEST_KEY:
            if QUEST_KIND_KEY not in data and QUEST_KIND_KEY not in out:
                out[QUEST_KIND_KEY] = value
            # else: canonical key already carries the value; drop the legacy one.
            continue
        out[key] = value
    return out, True


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

    Migrates a legacy ``quest:`` key to canonical ``quest-kind:`` as part of
    canonicalization, so any write-path workflow that routes frontmatter
    through here rewrites the note on touch (see issue #98).
    """
    data, _ = migrate_quest_kind(data)
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

"""Fence-aware task scanner + Obsidian Tasks emoji-date parsing.

Shared vault helper. Lifted from ``pqn-archive``'s private task handling
(``workflows/archive/steps``) so the read-only reporter (``pqn-tasks``)
and the archive task-cancellation path share one parser. A ``- [ ]``
inside a fenced code block is not a real task and is skipped.

Obsidian Tasks encodes scheduling metadata as trailing emoji + ISO date:
``📅`` due, ``⏳`` scheduled, ``🛫`` start (plus ``🔁`` recurrence and the
``✅``/``❌`` done/cancelled markers). This module parses the three date
fields; it does not interpret recurrence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# Obsidian Tasks emoji metadata.
DUE_EMOJI = "📅"
SCHEDULED_EMOJI = "⏳"
START_EMOJI = "🛫"
RECURRENCE_EMOJI = "🔁"
DONE_EMOJI = "✅"
CANCELLED_EMOJI = "❌"

# Presence of any of these on a line means it carries Tasks metadata we
# shouldn't silently bulldoze (used by pqn-archive's cancellation guard).
TASKS_META_EMOJI = (
    DUE_EMOJI,
    SCHEDULED_EMOJI,
    START_EMOJI,
    RECURRENCE_EMOJI,
    DONE_EMOJI,
    CANCELLED_EMOJI,
)

# Task states Obsidian Tasks treats as not-yet-done: ``[ ]`` open and
# ``[/]`` in-progress. ``[x]`` complete and ``[-]`` cancelled are done.
OPEN_STATES = (" ", "/")

# ``- [x] text`` / ``* [ ] text`` / ``+ [/] text``. Leading whitespace is
# allowed; the bullet and the single status char are captured.
_TASK_LINE = re.compile(r"^([ \t]*[-*+] )\[(.)\] (.*)$")
# A fenced code block opens with >= 3 backticks or tildes (optionally
# indented, optionally followed by an info string). It closes only on a
# line of the *same* character, at least as long, with nothing else on
# it (CommonMark). Tracking the run length keeps a 3-backtick line from
# closing a 4-backtick fence.
_FENCE_OPEN = re.compile(r"^[ \t]*(`{3,}|~{3,})")
_BLOCK_ID = re.compile(r"\s+\^([A-Za-z0-9-]+)\s*$")
# Trailing ``(?!\d)`` rejects typos like ``2026-07-170`` (which would
# otherwise match the ``2026-07-17`` prefix and report a bogus date).
_ISO_DATE = r"(\d{4}-\d{2}-\d{2})(?!\d)"


def _emoji_date_re(emoji: str) -> re.Pattern[str]:
    return re.compile(re.escape(emoji) + r"\s*" + _ISO_DATE)


_DUE_RE = _emoji_date_re(DUE_EMOJI)
_SCHEDULED_RE = _emoji_date_re(SCHEDULED_EMOJI)
_START_RE = _emoji_date_re(START_EMOJI)


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _find_date(pattern: re.Pattern[str], text: str) -> date | None:
    m = pattern.search(text)
    return _parse_iso(m.group(1)) if m else None


@dataclass
class ScannedTask:
    """One task line found in a note body.

    ``line`` is 1-based into the scanned ``body``. ``text`` is the raw
    remainder after the checkbox (including any emoji metadata and block
    id). ``description`` strips that metadata for display.
    """

    line: int
    bullet: str
    state: str
    text: str
    due: date | None = None
    scheduled: date | None = None
    start: date | None = None
    block_id: str | None = None

    @property
    def is_open(self) -> bool:
        return self.state in OPEN_STATES

    @property
    def description(self) -> str:
        """Task text with trailing Tasks emoji-metadata and block id removed."""
        cut = len(self.text)
        for emoji in TASKS_META_EMOJI:
            idx = self.text.find(emoji)
            if idx != -1:
                cut = min(cut, idx)
        desc = self.text[:cut]
        block = _BLOCK_ID.search(desc)
        if block is not None:
            desc = desc[: block.start()]
        return desc.strip()


def scan_tasks(body: str) -> list[ScannedTask]:
    """Return every task line in ``body`` that is outside a fenced code block.

    Includes all task states (open, in-progress, complete, cancelled,
    custom). Callers filter by :attr:`ScannedTask.is_open` when they only
    want actionable tasks. Fence handling matches Obsidian: a ``` or ~~~
    fence opens/closes a code block and its contents are never tasks.
    """
    found: list[ScannedTask] = []
    in_fence = False
    fence_char = ""
    fence_len = 0
    for idx, line in enumerate(body.splitlines(), start=1):
        if in_fence:
            stripped = line.strip()
            # Close only on a same-char run at least as long as the opener.
            if stripped and stripped == fence_char * len(stripped) and len(stripped) >= fence_len:
                in_fence = False
            # A line inside a fence is never a task.
            continue
        m_open = _FENCE_OPEN.match(line)
        if m_open is not None:
            run = m_open.group(1)
            in_fence = True
            fence_char = run[0]
            fence_len = len(run)
            # The opening fence line itself is never a task.
            continue
        m = _TASK_LINE.match(line)
        if m is None:
            continue
        text = m.group(3)
        block = _BLOCK_ID.search(text)
        found.append(
            ScannedTask(
                line=idx,
                bullet=m.group(1),
                state=m.group(2),
                text=text,
                due=_find_date(_DUE_RE, text),
                scheduled=_find_date(_SCHEDULED_RE, text),
                start=_find_date(_START_RE, text),
                block_id=block.group(1) if block is not None else None,
            )
        )
    return found

"""Batch-migrate legacy ``quest:`` frontmatter to canonical ``quest-kind:``.

This is the write half of ``pqn-validate`` (issue #97). Everything else in
the workflow is read-only; ``--fix`` is the one gesture that rewrites notes,
and only ever this single, lossless key rename.

Design:

* **Detect** via the ``legacy_quest_key`` check, so the file selection,
  template-skipping, and parse-safety rules stay in one place.
* **Guard** before rewriting ("don't guess", per #97): a note is migrated
  only when its legacy value is a valid kind (``main`` / ``side`` / ``none``),
  or when a canonical ``quest-kind:`` already exists (then the redundant
  legacy key is simply dropped). Any other value is reported and skipped.
* **Rewrite** structurally through :mod:`para_quest_notes.vault.frontmatter`
  (the single source of truth) using :func:`migrate_quest_kind`, which renames
  the key in place preserving order — no canonicalization, no reordering of
  other keys.
* **Dry-run by default.** ``apply=False`` reports what would change without
  touching disk; ``apply=True`` writes. Idempotent: a second run finds nothing.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from para_quest_notes.vault.frontmatter import (
    LEGACY_QUEST_KEY,
    parse,
)

from ._blocks import extract_blocks
from .checks import legacy_quest_key
from .pipeline import list_markdown_files

# The classifier enum. A legacy ``quest:`` carrying anything else is a note we
# refuse to guess about — reported and left untouched.
_VALID_KINDS = frozenset(("main", "side", "none"))

# A top-level ``quest`` key line inside the frontmatter block. Anchored at
# column 0 so nested ``quest:`` keys (e.g. under some other mapping) and the
# canonical ``quest-kind:`` are both left alone.
_LEGACY_KEY_LINE = re.compile(r"^quest([ \t]*):(.*)$")
_CANONICAL_KEY_LINE = re.compile(r"^quest-kind[ \t]*:")


@dataclass
class FixEntry:
    """One note the fixer migrated or deliberately skipped.

    ``action`` is ``"migrated"`` or ``"skipped"``. ``path`` is vault-relative
    POSIX. ``value`` is the legacy classifier value that drove the decision;
    ``reason`` explains a skip (empty for a migration).
    """

    path: str
    action: str
    value: Any = None
    reason: str = ""


@dataclass
class FixReport:
    """Result of a ``--fix`` run. Stable shape for JSON consumers."""

    vault: str
    applied: bool
    entries: list[FixEntry] = field(default_factory=list)

    @property
    def migrated(self) -> list[FixEntry]:
        return [e for e in self.entries if e.action == "migrated"]

    @property
    def skipped(self) -> list[FixEntry]:
        return [e for e in self.entries if e.action == "skipped"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "vault": self.vault,
            "applied": self.applied,
            "summary": {
                "migrated": len(self.migrated),
                "skipped": len(self.skipped),
            },
            "entries": [asdict(e) for e in self.entries],
        }


def migrate_note_text(text: str) -> tuple[str | None, Any, str]:
    """Rename a legacy ``quest:`` key in ``text``'s frontmatter to canonical.

    Pure and side-effect free so it's trivially testable. Returns
    ``(new_text, value, reason)``:

    * ``new_text`` is the rewritten note, or ``None`` when nothing should
      change (no frontmatter, no legacy key, or the value isn't a valid kind).
    * ``value`` is the legacy classifier value observed (for reporting).
    * ``reason`` is empty on success, or explains why the note was left alone.

    The rewrite is *surgical*: only the single legacy ``quest:`` line in the
    frontmatter block is renamed (or, when a canonical ``quest-kind:`` already
    exists, deleted). Every other byte — comments, quoting, scalar spelling,
    line endings, body, and any tail backmatter — is preserved exactly. We do
    not reserialize the YAML mapping (that would drop comments and can coerce
    scalars like ``yes`` or ``0123``).
    """
    parsed = parse(text)
    if not parsed.had_frontmatter or LEGACY_QUEST_KEY not in parsed.frontmatter:
        return None, None, "no legacy 'quest:' key in frontmatter"

    value = parsed.frontmatter[LEGACY_QUEST_KEY]
    blocks = extract_blocks(text)
    if blocks.frontmatter is None:  # pragma: no cover — parse() agreed there is one
        return None, value, "no frontmatter block found"

    # Frontmatter content lines are those strictly between the two ``---``
    # fences (start_line/end_line are 1-based and point at the fences).
    content_start = blocks.frontmatter.start_line  # 0-based index of first content line
    content_end = blocks.frontmatter.end_line - 2  # 0-based index of last content line

    lines = text.splitlines(keepends=True)
    has_canonical = any(
        _CANONICAL_KEY_LINE.match(_content(lines[i])) for i in range(content_start, content_end + 1)
    )

    # When a canonical key already exists it is authoritative; dropping the
    # redundant legacy key is always safe regardless of its stale value.
    if not has_canonical and not (isinstance(value, str) and value in _VALID_KINDS):
        return (
            None,
            value,
            f"legacy 'quest:' value {value!r} is not a valid kind (main/side/none); left unchanged",
        )

    out: list[str] = []
    for i, raw in enumerate(lines):
        if not (content_start <= i <= content_end):
            out.append(raw)
            continue
        body, eol = _split_eol(raw)
        m = _LEGACY_KEY_LINE.match(body)
        if not m:
            out.append(raw)
            continue
        if has_canonical:
            # Drop the redundant legacy line entirely.
            continue
        out.append(f"quest-kind{m.group(1)}:{m.group(2)}{eol}")

    return "".join(out), value, ""


def _content(raw: str) -> str:
    """The line's text with any trailing newline / carriage return removed."""
    return raw.rstrip("\n").rstrip("\r")


def _split_eol(raw: str) -> tuple[str, str]:
    """Split a raw line into (content, end-of-line) preserving CR/LF exactly."""
    body = _content(raw)
    return body, raw[len(body) :]


def fix_paths(vault: Path, files: list[Path], *, apply: bool) -> FixReport:
    """Migrate legacy ``quest:`` keys across ``files`` (absolute paths).

    Detection is delegated to the ``legacy_quest_key`` check so behavior can't
    drift from what ``pqn-validate`` reports. Only flagged notes are opened for
    rewriting.
    """
    report = FixReport(vault=str(vault), applied=apply)

    flagged = legacy_quest_key.run(vault, files, files)
    candidates = [vault / issue.path for issue in flagged]

    for path in candidates:
        rel = path.relative_to(vault).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            report.entries.append(
                FixEntry(path=rel, action="skipped", reason=f"could not read file: {exc}")
            )
            continue

        new_text, value, reason = migrate_note_text(text)
        if new_text is None:
            report.entries.append(FixEntry(path=rel, action="skipped", value=value, reason=reason))
            continue

        if apply:
            try:
                path.write_text(new_text, encoding="utf-8")
            except OSError as exc:
                report.entries.append(
                    FixEntry(path=rel, action="skipped", value=value, reason=f"write failed: {exc}")
                )
                continue

        report.entries.append(FixEntry(path=rel, action="migrated", value=value))

    return report


def fix_vault(
    vault: Path,
    *,
    paths: list[Path] | None = None,
    include_archive: bool = False,
    apply: bool = False,
) -> FixReport:
    """Entry point mirroring :func:`validate_vault`: build the focus set, fix it."""
    all_md = list_markdown_files(vault, include_archive=include_archive)
    if paths is None:
        focus = all_md
    else:
        focus = [p if p.is_absolute() else (vault / p).resolve() for p in paths]
    return fix_paths(vault, focus, apply=apply)

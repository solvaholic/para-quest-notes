"""Step 1: scan_note (pure).

Reads the inbox note from disk, splits frontmatter + body + legacy tail
backmatter, and detects sibling attachments (any non-``.md`` file in the
same directory whose stem starts with the note's stem — matches
Obsidian/markdown editors that pair ``Foo.md`` with ``Foo attachment.txt``,
``Foo.png``, etc.).

Frontmatter is canonical, so we use ``split_note`` rather than ``parse``:
``parsed.body`` excludes any deprecated trailing ``---...---`` block, and
``backmatter`` carries its keys for ``apply_move`` to fold into
frontmatter on touch (see ``docs/PLAN.md`` "Open questions — decided
2026-05-12" and issue #106).

Pure code; never escalates. Emits a ``ScanResult`` into the scratchpad
under ``ctx.scratchpad['scan']`` for downstream steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import ParsedNote, split_note


@dataclass
class ScanResult:
    source: Path
    parsed: ParsedNote
    attachments: list[Path] = field(default_factory=list)
    title: str = ""
    backmatter: dict[str, Any] = field(default_factory=dict)
    had_backmatter: bool = False

    def as_meta(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "had_frontmatter": self.parsed.had_frontmatter,
            "had_backmatter": self.had_backmatter,
            "attachments": [str(p.name) for p in self.attachments],
        }


class ScanNote:
    name = "scan_note"

    def __init__(self, source: Path):
        self.source = source

    def run(self, ctx: StepContext) -> StepResult:
        text = self.source.read_text(encoding="utf-8")
        split = split_note(text)
        parsed = ParsedNote(
            frontmatter=split.frontmatter,
            body=split.body,
            had_frontmatter=split.had_frontmatter,
        )
        attachments = _siblings(self.source)
        title = _title_from(parsed, self.source)
        result = ScanResult(
            source=self.source,
            parsed=parsed,
            attachments=attachments,
            title=title,
            backmatter=split.backmatter,
            had_backmatter=split.had_backmatter,
        )
        ctx.scratchpad["scan"] = result
        return StepResult(name=self.name, output=result, meta=result.as_meta())


def _siblings(source: Path) -> list[Path]:
    parent = source.parent
    stem = source.stem
    return sorted(
        p
        for p in parent.iterdir()
        if p.is_file()
        and p != source
        and p.suffix.lower() != ".md"
        and (p.stem == stem or p.stem.startswith(f"{stem} "))
    )


def _title_from(parsed: ParsedNote, source: Path) -> str:
    fm_title = parsed.frontmatter.get("title")
    if isinstance(fm_title, str) and fm_title.strip():
        return fm_title.strip()
    # First H1 in the body wins, otherwise the filename stem.
    for line in parsed.body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
    return source.stem

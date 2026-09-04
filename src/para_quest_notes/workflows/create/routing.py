"""Deterministic Markdown routing helpers for template merges."""

from __future__ import annotations

import re
from dataclasses import dataclass

_ATX_HEADING = re.compile(r"^ {0,3}(?P<marks>#{1,6})(?:[ \t]+(?P<title>.*?)|[ \t]*)$")
_CLOSING_MARKS = re.compile(r"[ \t]+#+[ \t]*$")
_CONTAINER_PREFIX = re.compile(r"^ {0,3}(?:>[ \t]?|(?:[-+*]|\d{1,9}[.)])[ \t]+)")
_BLOCKQUOTE_PREFIX = re.compile(r"^ {0,3}>[ \t]?")
_LIST_PREFIX = re.compile(r"^(?P<indent> *)(?:[-+*]|\d{1,9}[.)])(?P<spacing>[ \t]+)")


@dataclass(frozen=True)
class InputBlock:
    id: str
    text: str


@dataclass(frozen=True)
class TemplateSection:
    id: str
    heading: str
    level: int
    path: tuple[str, ...]
    line_index: int
    insert_at: int


def split_input_blocks(body: str) -> list[InputBlock]:
    """Split non-whitespace Markdown blocks while retaining their exact text."""
    blocks: list[InputBlock] = []
    current: list[str] = []
    fence: tuple[str, int] | None = None
    context = _FenceContext()

    def flush() -> None:
        if not current:
            return
        text = "".join(current)
        blocks.append(InputBlock(id=f"block-{len(blocks) + 1:03d}", text=text))
        current.clear()

    for line in body.splitlines(keepends=True):
        marker = context.marker(line.rstrip("\r\n"), in_fence=fence is not None)
        if fence is not None:
            current.append(line)
            if (
                marker is not None
                and marker[0] == fence[0]
                and marker[1] >= fence[1]
                and not marker[2].strip()
            ):
                fence = None
        elif marker is not None:
            current.append(line)
            fence = (marker[0], marker[1])
        elif line.strip():
            current.append(line)
        else:
            flush()
    flush()

    if not blocks and body.strip():
        blocks.append(InputBlock(id="block-001", text=body))
    return blocks


def catalog_template_sections(body: str) -> list[TemplateSection]:
    """Catalog ATX headings outside fenced code, including nested paths."""
    lines = body.splitlines(keepends=True)
    found: list[tuple[int, str, int, tuple[str, ...]]] = []
    stack: list[tuple[int, str]] = []
    fence: tuple[str, int] | None = None
    context = _FenceContext()

    for line_index, line in enumerate(lines):
        raw = line.rstrip("\r\n")
        marker = context.marker(raw, in_fence=fence is not None)
        if fence is not None:
            if (
                marker is not None
                and marker[0] == fence[0]
                and marker[1] >= fence[1]
                and not marker[2].strip()
            ):
                fence = None
            continue
        if marker is not None:
            fence = (marker[0], marker[1])
            continue

        match = _ATX_HEADING.match(raw)
        if match is None:
            continue
        level = len(match.group("marks"))
        heading = _CLOSING_MARKS.sub("", match.group("title") or "").strip()
        stack = [
            (ancestor_level, title) for ancestor_level, title in stack if ancestor_level < level
        ]
        stack.append((level, heading))
        found.append((line_index, heading, level, tuple(title for _, title in stack)))

    sections: list[TemplateSection] = []
    for index, (line_index, heading, level, path) in enumerate(found):
        insert_at = found[index + 1][0] if index + 1 < len(found) else len(lines)
        sections.append(
            TemplateSection(
                id=f"section-{index + 1:03d}",
                heading=heading,
                level=level,
                path=path,
                line_index=line_index,
                insert_at=insert_at,
            )
        )
    return sections


def merge_routed_blocks(
    template_body: str,
    *,
    sections: list[TemplateSection],
    blocks: list[InputBlock],
    assignments: dict[str, str],
) -> str:
    """Insert original blocks according to a validated ID-only routing plan."""
    existing_unsorted = next(
        (section for section in sections if section.heading.casefold() == "unsorted"),
        None,
    )
    by_section: dict[str, list[InputBlock]] = {}
    unsorted: list[InputBlock] = []
    for block in blocks:
        target = assignments[block.id]
        if target == "unsorted" and existing_unsorted is not None:
            by_section.setdefault(existing_unsorted.id, []).append(block)
        elif target == "unsorted":
            unsorted.append(block)
        else:
            by_section.setdefault(target, []).append(block)

    lines = template_body.splitlines(keepends=True)
    section_by_id = {section.id: section for section in sections}
    insertions = sorted(
        (
            section_by_id[section_id].insert_at,
            _join_blocks(section_blocks),
        )
        for section_id, section_blocks in by_section.items()
    )

    parts: list[str] = []
    cursor = 0
    for line_index, payload in insertions:
        parts.append("".join(lines[cursor:line_index]))
        right_exists = line_index < len(lines)
        parts.append(_separate("".join(parts), payload, right_exists=right_exists))
        cursor = line_index
    parts.append("".join(lines[cursor:]))
    merged = "".join(parts)

    if unsorted:
        unsorted_section = "## Unsorted\n\n" + _join_blocks(unsorted)
        merged += _separate(merged, unsorted_section, right_exists=False)
    return merged


class _FenceContext:
    def __init__(self) -> None:
        self._list_indents: list[int] = []
        self._blank_lines = 0

    def marker(self, line: str, *, in_fence: bool) -> tuple[str, int, str] | None:
        if not in_fence:
            self._update_list_context(line)
        max_indent = self._list_indents[-1] + 3 if self._list_indents else 3
        return _fence_marker(line, max_indent=max_indent)

    def _update_list_context(self, line: str) -> None:
        candidate = line
        while match := _BLOCKQUOTE_PREFIX.match(candidate):
            candidate = candidate[match.end() :]

        if not candidate.strip():
            self._blank_lines += 1
            return
        if self._blank_lines >= 2:
            self._list_indents.clear()
        self._blank_lines = 0

        leading_spaces = len(candidate) - len(candidate.lstrip(" "))
        match = _LIST_PREFIX.match(candidate)
        allowed_indent = self._list_indents[-1] + 3 if self._list_indents else 3
        if match is not None and leading_spaces <= allowed_indent:
            marker_indent = len(match.group("indent"))
            while self._list_indents and self._list_indents[-1] > marker_indent:
                self._list_indents.pop()
            content_indent = match.end()
            if not self._list_indents or content_indent > self._list_indents[-1]:
                self._list_indents.append(content_indent)
            else:
                self._list_indents[-1] = content_indent
            return

        while self._list_indents and leading_spaces < self._list_indents[-1]:
            self._list_indents.pop()


def _fence_marker(line: str, *, max_indent: int = 3) -> tuple[str, int, str] | None:
    candidate = line
    while True:
        match = _CONTAINER_PREFIX.match(candidate)
        if match is None:
            break
        candidate = candidate[match.end() :]

    stripped = candidate.lstrip(" ")
    if len(candidate) - len(stripped) > max_indent or not stripped or stripped[0] not in ("`", "~"):
        return None
    marker = stripped[0]
    count = len(stripped) - len(stripped.lstrip(marker))
    if count < 3:
        return None
    return marker, count, stripped[count:]


def _join_blocks(blocks: list[InputBlock]) -> str:
    merged = ""
    for block in blocks:
        merged += _separate(merged, block.text, right_exists=False)
    return merged


def _separate(left: str, payload: str, *, right_exists: bool) -> str:
    prefix = ""
    if left and not left.endswith("\n\n"):
        prefix = "\n" if left.endswith("\n") else "\n\n"

    suffix = ""
    if right_exists:
        if not payload.endswith("\n\n"):
            suffix = "\n" if payload.endswith("\n") else "\n\n"
    elif not payload.endswith("\n"):
        suffix = "\n"
    return prefix + payload + suffix


__all__ = [
    "InputBlock",
    "TemplateSection",
    "catalog_template_sections",
    "merge_routed_blocks",
    "split_input_blocks",
]

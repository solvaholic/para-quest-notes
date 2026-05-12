"""Extract YAML frontmatter and (optional) backmatter blocks from a note.

This is more permissive than :mod:`para_quest_notes.vault.frontmatter`
on purpose: that module silently treats malformed YAML as "no
frontmatter" so callers can keep editing the body. Validation needs
the opposite — surface the YAML error with a line number.

The parser here is intentionally line-based and dumb. It does not care
about Markdown semantics, only ``---``-delimited blocks at the very top
and very bottom of the file.
"""

from __future__ import annotations

from dataclasses import dataclass

DELIM = "---"


@dataclass
class Block:
    """A YAML-fenced block within a note.

    ``text`` is the YAML content between the delimiters (no trailing
    newline guaranteed). ``start_line`` is 1-based and points at the
    opening ``---`` line. ``end_line`` points at the closing ``---``.
    """

    text: str
    start_line: int
    end_line: int


@dataclass
class NoteBlocks:
    frontmatter: Block | None = None
    backmatter: Block | None = None
    # True when the file starts with `---` but no closing fence was found.
    frontmatter_unterminated: bool = False


def extract_blocks(text: str) -> NoteBlocks:
    """Locate the frontmatter (top) and backmatter (bottom) YAML fences.

    Frontmatter rules:
        * The file must start with a line equal to ``---`` (no leading
          blank lines — matches the existing parser).
        * The first subsequent ``---`` line closes it.

    Backmatter rules:
        * The file's last non-blank line must be exactly ``---``.
        * Walking upward from there, the next ``---`` line opens it.
        * The opener must come *after* the frontmatter close (if any),
          and there must be at least one non-fence line between opener
          and closer (a ``---`` directly above ``---`` is not backmatter).
    """
    lines = text.splitlines()
    blocks = NoteBlocks()
    if not lines:
        return blocks

    # ---- frontmatter ----
    fm_close_idx: int | None = None
    if lines[0].rstrip("\r") == DELIM:
        for i in range(1, len(lines)):
            if lines[i].rstrip("\r") == DELIM:
                fm_close_idx = i
                break
        if fm_close_idx is None:
            blocks.frontmatter_unterminated = True
        else:
            fm_text = "\n".join(lines[1:fm_close_idx])
            blocks.frontmatter = Block(
                text=fm_text,
                start_line=1,
                end_line=fm_close_idx + 1,
            )

    # ---- backmatter ----
    last_idx = len(lines) - 1
    while last_idx >= 0 and lines[last_idx].strip() == "":
        last_idx -= 1
    if last_idx <= (fm_close_idx if fm_close_idx is not None else 0):
        return blocks
    if lines[last_idx].rstrip("\r") != DELIM:
        return blocks

    open_idx: int | None = None
    earliest = (fm_close_idx + 1) if fm_close_idx is not None else 0
    for i in range(last_idx - 1, earliest - 1, -1):
        if lines[i].rstrip("\r") == DELIM:
            open_idx = i
            break
    if open_idx is None or open_idx == last_idx - 1:
        return blocks

    bm_text = "\n".join(lines[open_idx + 1 : last_idx])
    blocks.backmatter = Block(
        text=bm_text,
        start_line=open_idx + 1,
        end_line=last_idx + 1,
    )
    return blocks

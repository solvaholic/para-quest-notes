"""Render a :class:`QuestIndex` as markdown, ready to redirect into a note.

Layout is **flat**: one ``##`` section per declared Quest (Main Quests
first, then Side Quests), each listing the notes that roll up under it as
wikilinks. Capabilities and Unassigned follow as their own ``##`` sections.
A note supporting two Quests appears under both — intentional, and the
reason JSON (not markdown) is the machine-readable surface.
"""

from __future__ import annotations

from .contract import NoteEntry, QuestIndex


def _bullet(note: NoteEntry) -> str:
    """One list item: a wikilink, with a light type hint for the mixed lists."""
    if note.type in ("area", "project", "resource"):
        return f"- [[{note.title}]] ({note.type})"
    return f"- [[{note.title}]]"


def _section(title: str, notes: list[NoteEntry]) -> list[str]:
    lines = [f"## {title}", ""]
    if notes:
        lines.extend(_bullet(n) for n in notes)
    else:
        lines.append("_none_")
    lines.append("")
    return lines


def render_markdown(index: QuestIndex) -> str:
    """Render the index. Always ends with a single trailing newline."""
    lines: list[str] = ["# Quest index", ""]

    quest_filter = index.scope.get("quest")
    for quest in index.quests:
        if quest_filter is not None and quest.name.lower() != quest_filter:
            # Under --quest, emit only the requested Quest's section — a note
            # supporting several Quests must not drag its other sections in.
            continue
        lines.extend(_section(f"[[{quest.name}]]", index.notes_for_quest(quest.name)))

    # Capabilities and Unassigned are omitted entirely under --quest (they
    # don't belong to a single Quest).
    if quest_filter is None:
        capabilities = index.capabilities
        if capabilities:
            lines.extend(_section("Capabilities", capabilities))
        unassigned = index.unassigned
        if unassigned:
            lines.extend(_section("Unassigned", unassigned))

    text = "\n".join(lines).rstrip("\n")
    return text + "\n"

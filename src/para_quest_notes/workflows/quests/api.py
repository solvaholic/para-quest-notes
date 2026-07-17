"""Library entry point for ``pqn-quests``.

Agents and other workflows build the Quest index by calling
:func:`build_quest_index` directly rather than shelling out to the CLI.
"""

from __future__ import annotations

from .builder import build_quest_index
from .contract import NoteEntry, QuestIndex, QuestRef
from .render import render_markdown

__all__ = [
    "NoteEntry",
    "QuestIndex",
    "QuestRef",
    "build_quest_index",
    "render_markdown",
]

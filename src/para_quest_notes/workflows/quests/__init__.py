"""``pqn-quests`` — generate the Main Quest index from the vault (no LLM).

Read-only and stateless: walks the vault, groups notes by the Quest(s)
they support, and prints the rollup as markdown (default) or flat JSON.
It never creates or owns an index note — redirect the markdown into
whatever note you like:

    pqn-quests --format text > index.md

See ``docs/workflows/quests.md``.
"""

from para_quest_notes.workflows.quests.api import (
    build_quest_index,
    render_markdown,
)
from para_quest_notes.workflows.quests.contract import (
    NoteEntry,
    QuestIndex,
    QuestRef,
)

__all__ = [
    "NoteEntry",
    "QuestIndex",
    "QuestRef",
    "build_quest_index",
    "render_markdown",
]

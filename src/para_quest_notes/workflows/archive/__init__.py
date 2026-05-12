"""``pqn-archive`` workflow.

Move a completed Project note from ``projects/`` to
``archive/projects/`` while freezing its task state and recording an
``## Outcome`` section. Projects only in v1; Areas/Resources escalate.
"""

from para_quest_notes.workflows.archive.contract import (
    ArchiveInputs,
    ArchiveResult,
)
from para_quest_notes.workflows.archive.pipeline import archive_note

__all__ = ["ArchiveInputs", "ArchiveResult", "archive_note"]

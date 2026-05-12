"""``pqn-create`` workflow.

Author a single new note directly into its PARA home, with canonical
frontmatter and a type-appropriate body skeleton. No LLM in this slice
— the user supplies type + title + supports up front.
"""

from para_quest_notes.workflows.create.contract import (
    CreateInputs,
    CreateResult,
)
from para_quest_notes.workflows.create.pipeline import create_note

__all__ = ["CreateInputs", "CreateResult", "create_note"]

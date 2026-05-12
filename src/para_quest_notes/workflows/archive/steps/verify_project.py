"""Step 2: verify_project (pure).

Parses the target's metadata (frontmatter, plus deprecated tail
backmatter for legacy notes) and verifies ``type: project``.
Areas/Resources/anything-else escalate — pqn-archive v1 is Projects
only.

Also collects everything compose_archive needs in one read: the parsed
front/back blocks, the body, and a flag for whether backmatter was
present (so the apply step can record ``frontmatter_migrated``).
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import merge, split_note


class VerifyProject:
    name = "verify_project"

    def run(self, ctx: StepContext) -> StepResult:
        source: Path = ctx.scratchpad["source_abs"]
        text = source.read_text(encoding="utf-8")
        split = split_note(text)
        # Merge front + back so legacy notes with only-backmatter type:
        # are honored. Frontmatter wins on conflict (it's canonical).
        combined = merge(split.backmatter, split.frontmatter)
        note_type = combined.get("type")

        if note_type is None:
            raise EscalateToUser(
                step=self.name,
                reason="note has no type: in front- or backmatter; "
                "normalize it (e.g. run pqn-ingest) before archiving",
                options=[],
                context={"source": ctx.scratchpad["source_rel"]},
            )
        if note_type != "project":
            raise EscalateToUser(
                step=self.name,
                reason=f"pqn-archive v1 is Projects only (got type={note_type!r})",
                options=[],
                context={"source": ctx.scratchpad["source_rel"], "type": note_type},
            )

        ctx.scratchpad["split"] = split
        ctx.scratchpad["combined_metadata"] = combined
        ctx.scratchpad["original_text"] = text
        return StepResult(
            name=self.name,
            output={"type": "project", "had_backmatter": split.had_backmatter},
            meta={"had_backmatter": split.had_backmatter},
        )

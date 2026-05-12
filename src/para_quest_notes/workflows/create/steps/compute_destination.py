"""Step 2: compute_destination (pure).

Maps ``(type, sub_path, title)`` to the vault-relative path
``<type>s/[sub_path/]<Title>.md``. The vault root contains ``projects/``,
``areas/``, ``resources/`` as siblings (per docs/notes-system.md
"Directory layout").
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.create.contract import CreateInputs


class ComputeDestination:
    name = "compute_destination"

    def run(self, ctx: StepContext) -> StepResult:
        inputs: CreateInputs = ctx.scratchpad["inputs"]
        title: str = ctx.scratchpad["title"]
        sub_path: str = ctx.scratchpad.get("sub_path", "")

        if ctx.vault is None:
            raise EscalateToUser(
                step=self.name,
                reason="no vault path resolved",
                options=[],
                context={},
            )

        para_dir = f"{inputs.type}s"  # project -> projects, area -> areas, resource -> resources
        filename = f"{title}.md"
        rel_parts = [para_dir]
        if sub_path:
            rel_parts.extend(p for p in sub_path.split("/") if p)
        rel_parts.append(filename)
        destination = "/".join(rel_parts)

        ctx.scratchpad["filename"] = filename
        ctx.scratchpad["destination"] = destination
        ctx.scratchpad["destination_abs"] = Path(ctx.vault, *rel_parts)
        return StepResult(
            name=self.name,
            output={"filename": filename, "destination": destination},
            meta={"destination": destination},
        )

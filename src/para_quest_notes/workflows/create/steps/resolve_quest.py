"""Step 1.5: resolve_quest (pure, no-LLM).

When ``--supports`` is omitted for a project/area note, tries to
resolve the Quest deterministically from the destination path using
:func:`~para_quest_notes.vault.quests.resolve_quest_from_path`.

On a hit, fills in ``supports`` on the scratchpad inputs so
``compute_destination`` sends the note to its canonical location
instead of inbox. On a miss, leaves inputs unchanged (inbox fallback).

This step runs after ``validate_inputs`` (which normalizes the inputs
and records the inbox-fallback note) and before ``compute_destination``.
"""

from __future__ import annotations

from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.quests import discover_quests, resolve_quest_from_path
from para_quest_notes.workflows.create.contract import CreateInputs


class ResolveQuest:
    name = "resolve_quest"

    def run(self, ctx: StepContext) -> StepResult:
        inputs: CreateInputs = ctx.scratchpad["inputs"]

        # Only attempt resolution when supports is missing for project/area
        if inputs.supports or inputs.type not in ("project", "area"):
            return StepResult(
                name=self.name,
                output={"skipped": True, "reason": "supports already provided"},
            )

        if ctx.vault is None:
            return StepResult(
                name=self.name,
                output={"skipped": True, "reason": "no vault"},
            )

        # Build the candidate destination path for the resolver
        title: str = ctx.scratchpad["title"]
        sub_path: str = ctx.scratchpad.get("sub_path", "")
        para_dir = f"{inputs.type}s"
        path_parts = [para_dir]
        if sub_path:
            path_parts.extend(p for p in sub_path.split("/") if p)
        path_parts.append(f"{title}.md")
        dest_path = "/".join(path_parts)

        # Get valid quest names from the vault
        vault_quests = discover_quests(ctx.vault)
        if not vault_quests:
            return StepResult(
                name=self.name,
                output={"resolved": False, "reason": "no quests declared in vault"},
            )
        valid_names = {q.name for q in vault_quests}

        # Try deterministic resolution
        resolved = resolve_quest_from_path(ctx.vault, dest_path, valid_quests=valid_names)
        if not resolved.quests:
            return StepResult(
                name=self.name,
                output={"resolved": False, "reason": "deterministic miss"},
                meta={"source": "miss"},
            )

        # Hit! Update inputs with the resolved supports
        supports = [f"[[{q}]]" for q in resolved.quests]
        updated_inputs = CreateInputs(
            title=inputs.title,
            type=inputs.type,
            quest=inputs.quest,
            supports=supports,
            sub_path=inputs.sub_path,
            source_url=inputs.source_url,
            body=inputs.body,
        )
        ctx.scratchpad["inputs"] = updated_inputs

        # Clear the inbox-fallback note since we resolved the quest
        plan_notes: list[str] = ctx.scratchpad.get("plan_notes", [])
        ctx.scratchpad["plan_notes"] = [n for n in plan_notes if "filed to inbox" not in n]

        return StepResult(
            name=self.name,
            output={
                "resolved": True,
                "quests": resolved.quests,
                "supports": supports,
                "source": resolved.source,
            },
            meta={
                "quests": resolved.quests,
                "source": resolved.source,
                "dest_path": dest_path,
            },
        )

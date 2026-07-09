"""Pipeline assembly for ``pqn-create``.

One pipeline per invocation. No vault-wide pre-pass needed (unlike
``pqn-ingest`` which discovers Quests once); collision detection scans
the vault inside the ``check_collision`` step.
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.step import Workflow, WorkflowResult
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.workflows.create.contract import (
    CreateInputs,
    CreatePlan,
    CreateResult,
)
from para_quest_notes.workflows.create.steps.check_collision import CheckCollision
from para_quest_notes.workflows.create.steps.compose_note import ComposeNote
from para_quest_notes.workflows.create.steps.compute_destination import ComputeDestination
from para_quest_notes.workflows.create.steps.resolve_quest import ResolveQuest
from para_quest_notes.workflows.create.steps.validate_after import ValidateAfter
from para_quest_notes.workflows.create.steps.validate_inputs import ValidateInputs
from para_quest_notes.workflows.create.steps.write_note import WriteNote


def build_workflow(inputs: CreateInputs, *, apply: bool, today: str | None = None) -> Workflow:
    return Workflow(
        name="create",
        steps=[
            ValidateInputs(inputs),
            ResolveQuest(),
            ComputeDestination(),
            CheckCollision(),
            ComposeNote(today=today),
            WriteNote(apply=apply),
            ValidateAfter(apply=apply),
        ],
    )


def create_note(
    inputs: CreateInputs,
    *,
    vault: Path,
    apply: bool = False,
    config: Config | None = None,
    trace: TraceWriter | None = None,
    today: str | None = None,
) -> CreateResult:
    """Run the create-note workflow once. Returns a structured result.

    ``today`` is injectable so tests can pin the ``created:`` field.
    """
    wf = build_workflow(inputs, apply=apply, today=today)
    wf_result = wf.run(vault=vault, config=config, trace=trace)
    return _to_create_result(wf_result, vault=vault, apply=apply)


def _to_create_result(wf: WorkflowResult, *, vault: Path, apply: bool) -> CreateResult:
    plan = CreatePlan()
    written = False

    for step in wf.steps:
        if step.name == "validate_inputs" and isinstance(step.output, dict):
            plan.notes.extend(str(note) for note in step.output.get("notes") or [])
        elif step.name == "resolve_quest" and isinstance(step.output, dict):
            if step.output.get("resolved"):
                # Quest was resolved - replace the inbox note with a resolution note
                plan.notes = [n for n in plan.notes if "filed to inbox" not in n]
                source = step.output.get("source", "")
                quests = step.output.get("quests", [])
                plan.notes.append(f"quest resolved via {source}: {', '.join(quests)}")
        elif step.name == "compute_destination" and isinstance(step.output, dict):
            plan.filename = step.output.get("filename")
            plan.destination = step.output.get("destination")
            plan.destination_mode = step.output.get("destination_mode")
        elif step.name == "compose_note" and isinstance(step.output, dict):
            plan.frontmatter = dict(step.output.get("frontmatter") or {})
        elif step.name == "write_note" and isinstance(step.output, dict):
            written = bool(step.output.get("written"))

    return CreateResult(
        vault=str(vault),
        apply=apply,
        ok=wf.ok,
        plan=plan,
        written=written,
        escalation=wf.escalation,
        error=wf.error,
        run_id=wf.run_id,
    )

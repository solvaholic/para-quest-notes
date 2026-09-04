"""Pipeline assembly for ``pqn-create``.

One pipeline per invocation. No vault-wide pre-pass needed (unlike
``pqn-ingest`` which discovers Quests once); collision detection scans
the vault inside the ``check_collision`` step.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.prompts import PromptLoader
from para_quest_notes.adapter.step import Workflow, WorkflowResult
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.workflows.create.contract import (
    CreateInputs,
    CreatePlan,
    CreateResult,
    TemplateMergePlan,
)
from para_quest_notes.workflows.create.steps.check_collision import CheckCollision
from para_quest_notes.workflows.create.steps.compose_note import ComposeNote
from para_quest_notes.workflows.create.steps.compute_destination import ComputeDestination
from para_quest_notes.workflows.create.steps.merge_template import MergeTemplate
from para_quest_notes.workflows.create.steps.resolve_quest import ResolveQuest
from para_quest_notes.workflows.create.steps.validate_after import ValidateAfter
from para_quest_notes.workflows.create.steps.validate_inputs import ValidateInputs
from para_quest_notes.workflows.create.steps.write_note import WriteNote

PROMPTS_DIR = Path(__file__).parent / "prompts"


def build_workflow(
    inputs: CreateInputs,
    *,
    apply: bool,
    today: str | None = None,
    model: str | None = None,
) -> Workflow:
    resolved_today = today or date.today().isoformat()
    loader = PromptLoader(PROMPTS_DIR)
    return Workflow(
        name="create",
        steps=[
            ValidateInputs(inputs),
            ResolveQuest(),
            ComputeDestination(),
            CheckCollision(),
            MergeTemplate(
                prompt=loader.get("merge_template"),
                today=resolved_today,
                apply=apply,
                model=model,
            ),
            ComposeNote(today=resolved_today),
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
    llm: Any = None,
    model: str | None = None,
) -> CreateResult:
    """Run the create-note workflow once. Returns a structured result.

    ``today`` is injectable so tests can pin the ``created:`` field.
    """
    wf = build_workflow(inputs, apply=apply, today=today, model=model)
    wf_result = wf.run(vault=vault, config=config, llm=llm, trace=trace)
    return _to_create_result(
        wf_result,
        vault=vault,
        apply=apply,
        merge_requested=inputs.merge_template,
        requested_template=inputs.template,
    )


def _to_create_result(
    wf: WorkflowResult,
    *,
    vault: Path,
    apply: bool,
    merge_requested: bool,
    requested_template: str | None,
) -> CreateResult:
    plan = CreatePlan(
        template_merge=(
            TemplateMergePlan(status="failed", template=requested_template)
            if merge_requested
            else None
        )
    )
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
        elif step.name == "merge_template" and isinstance(step.output, dict):
            merge_status = step.output.get("status")
            if merge_status == "deferred":
                plan.template_merge = TemplateMergePlan(
                    status="deferred",
                    template=str(step.output["template"]),
                    input_blocks=int(step.output["input_blocks"]),
                )
            elif merge_status == "merged":
                plan.template_merge = TemplateMergePlan(
                    status="merged",
                    template=str(step.output["template"]),
                    input_blocks=int(step.output["input_blocks"]),
                    routed_blocks=int(step.output["routed_blocks"]),
                    unsorted_blocks=int(step.output["unsorted_blocks"]),
                )
        elif step.name == "compose_note" and isinstance(step.output, dict):
            plan.frontmatter = dict(step.output.get("frontmatter") or {})
            body_source = step.output.get("body_source")
            plan.body_source = str(body_source) if body_source is not None else None
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

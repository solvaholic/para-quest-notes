"""Pipeline assembly for ``pqn-daily``."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.step import Workflow, WorkflowResult
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.workflows.daily.contract import (
    DailyInputs,
    DailyPlan,
    DailyResult,
)
from para_quest_notes.workflows.daily.steps.check_collision import CheckCollision
from para_quest_notes.workflows.daily.steps.compose_note import ComposeNote
from para_quest_notes.workflows.daily.steps.compute_destination import ComputeDestination
from para_quest_notes.workflows.daily.steps.detect_shape import DetectShape
from para_quest_notes.workflows.daily.steps.inspect_parent import InspectParent
from para_quest_notes.workflows.daily.steps.move_file import MoveFile
from para_quest_notes.workflows.daily.steps.resolve_target import ResolveTarget
from para_quest_notes.workflows.daily.steps.validate_after import ValidateAfter


def build_workflow(inputs: DailyInputs, *, apply: bool) -> Workflow:
    return Workflow(
        name="daily",
        steps=[
            ResolveTarget(inputs.target),
            DetectShape(),
            InspectParent(),
            ComputeDestination(),
            CheckCollision(),
            ComposeNote(),
            MoveFile(apply=apply),
            ValidateAfter(apply=apply),
        ],
    )


def file_daily_note(
    inputs: DailyInputs,
    *,
    vault: Path,
    apply: bool = False,
    config: Config | None = None,
    trace: TraceWriter | None = None,
) -> DailyResult:
    """Run the daily-filing workflow once. Returns a structured result."""
    wf = build_workflow(inputs, apply=apply)
    wf_result = wf.run(vault=vault, config=config, trace=trace)
    return _to_daily_result(wf_result, vault=vault, apply=apply)


def _to_daily_result(wf: WorkflowResult, *, vault: Path, apply: bool) -> DailyResult:
    plan = DailyPlan()
    moved = False

    for step in wf.steps:
        if step.name == "resolve_target" and isinstance(step.output, dict):
            plan.source = step.output.get("source")
        elif step.name == "detect_shape" and isinstance(step.output, dict):
            plan.date = step.output.get("date")
        elif step.name == "compute_destination" and isinstance(step.output, dict):
            plan.destination = step.output.get("destination")
            plan.already_at_destination = bool(step.output.get("already_at_destination"))
        elif step.name == "compose_note" and isinstance(step.output, dict):
            plan.h1_inserted = bool(step.output.get("h1_inserted"))
            plan.frontmatter_migrated = bool(step.output.get("frontmatter_migrated"))
        elif step.name == "move_file" and isinstance(step.output, dict):
            moved = bool(step.output.get("moved"))

    return DailyResult(
        vault=str(vault),
        apply=apply,
        ok=wf.ok,
        plan=plan,
        moved=moved,
        escalation=wf.escalation,
        error=wf.error,
        run_id=wf.run_id,
    )

"""Pipeline assembly for ``pqn-daily``."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.step import Step, Workflow, WorkflowResult
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.workflows.daily.contract import (
    DailyInputs,
    DailyPlan,
    DailyResult,
    TaskRoundupAction,
    TaskRoundupResult,
)
from para_quest_notes.workflows.daily.steps.check_collision import CheckCollision
from para_quest_notes.workflows.daily.steps.compose_note import ComposeNote
from para_quest_notes.workflows.daily.steps.compose_task_roundup import ComposeTaskRoundup
from para_quest_notes.workflows.daily.steps.compute_destination import ComputeDestination
from para_quest_notes.workflows.daily.steps.detect_shape import DetectShape
from para_quest_notes.workflows.daily.steps.inspect_parent import InspectParent
from para_quest_notes.workflows.daily.steps.move_file import MoveFile
from para_quest_notes.workflows.daily.steps.resolve_target import ResolveTarget
from para_quest_notes.workflows.daily.steps.validate_after import ValidateAfter
from para_quest_notes.workflows.tasks.settings import resolve_date_fields


def build_workflow(
    inputs: DailyInputs,
    *,
    apply: bool,
    task_date_fields: Sequence[str] | None = None,
) -> Workflow:
    steps: list[Step] = [
        ResolveTarget(inputs.target, create_missing=inputs.create_missing),
        DetectShape(),
        InspectParent(),
        ComputeDestination(),
        CheckCollision(),
        ComposeNote(),
    ]
    if inputs.task_roundup:
        if task_date_fields is None:  # pragma: no cover - resolved by file_daily_note
            raise RuntimeError("task date fields were not resolved")
        steps.append(
            ComposeTaskRoundup(
                date_fields=task_date_fields,
                apply=apply,
            )
        )
    steps.extend([MoveFile(apply=apply), ValidateAfter(apply=apply)])
    return Workflow(
        name="daily",
        steps=steps,
    )


def file_daily_note(
    inputs: DailyInputs,
    *,
    vault: Path,
    apply: bool = False,
    config: Config | None = None,
    trace: TraceWriter | None = None,
    task_date_fields: Sequence[str] | None = None,
) -> DailyResult:
    """Run the daily-filing workflow once. Returns a structured result."""
    if inputs.task_roundup and task_date_fields is None:
        workflows = config.workflows if config is not None else {}
        task_date_fields = resolve_date_fields(None, workflows)
    wf = build_workflow(
        inputs,
        apply=apply,
        task_date_fields=task_date_fields,
    )
    wf_result = wf.run(vault=vault, config=config, trace=trace)
    return _to_daily_result(wf_result, vault=vault, apply=apply)


def _to_daily_result(wf: WorkflowResult, *, vault: Path, apply: bool) -> DailyResult:
    plan = DailyPlan()
    moved = False
    created = False
    task_roundup = None

    for step in wf.steps:
        if step.name == "resolve_target" and isinstance(step.output, dict):
            plan.source = step.output.get("source")
            plan.would_create = bool(step.output.get("missing"))
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
            created = bool(step.output.get("created"))
        elif step.name == "compose_task_roundup" and isinstance(step.output, dict):
            task_roundup = TaskRoundupResult(
                action=cast(TaskRoundupAction, step.output["action"]),
                applied=bool(step.output["applied"]),
                reference_date=str(step.output["reference_date"]),
                due_in=int(step.output["due_in"]),
                group_by=str(step.output["group_by"]),
                date_fields=list(step.output["date_fields"]),
                include_archive=bool(step.output["include_archive"]),
                unscheduled=str(step.output["unscheduled"]),
                files_scanned=int(step.output["files_scanned"]),
                summary=dict(step.output["summary"]),
            )

    return DailyResult(
        vault=str(vault),
        apply=apply,
        ok=wf.ok,
        plan=plan,
        moved=moved,
        created=created,
        task_roundup=task_roundup,
        escalation=wf.escalation,
        error=wf.error,
        run_id=wf.run_id,
    )

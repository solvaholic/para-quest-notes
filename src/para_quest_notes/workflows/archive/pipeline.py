"""Pipeline assembly for ``pqn-archive``."""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.step import Workflow, WorkflowResult
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.workflows.archive.contract import (
    ArchiveInputs,
    ArchivePlan,
    ArchiveResult,
)
from para_quest_notes.workflows.archive.steps.compose_archive import ComposeArchive
from para_quest_notes.workflows.archive.steps.decide_task_action import DecideTaskAction
from para_quest_notes.workflows.archive.steps.prepare_outcome import PrepareOutcome
from para_quest_notes.workflows.archive.steps.resolve_target import ResolveTarget
from para_quest_notes.workflows.archive.steps.scan_open_tasks import ScanOpenTasks
from para_quest_notes.workflows.archive.steps.validate_after import ValidateAfter
from para_quest_notes.workflows.archive.steps.verify_project import VerifyProject
from para_quest_notes.workflows.archive.steps.write_and_move import WriteAndMove


def build_workflow(
    inputs: ArchiveInputs,
    *,
    apply: bool,
    today: str | None = None,
) -> Workflow:
    return Workflow(
        name="archive",
        steps=[
            ResolveTarget(inputs.target),
            VerifyProject(),
            ScanOpenTasks(),
            DecideTaskAction(cancel_open_tasks=inputs.cancel_open_tasks),
            PrepareOutcome(outcome=inputs.outcome),
            ComposeArchive(today=today),
            WriteAndMove(apply=apply),
            ValidateAfter(apply=apply),
        ],
    )


def archive_note(
    inputs: ArchiveInputs,
    *,
    vault: Path,
    apply: bool = False,
    config: Config | None = None,
    trace: TraceWriter | None = None,
    today: str | None = None,
) -> ArchiveResult:
    """Run the archive workflow once. Returns a structured result."""
    wf = build_workflow(inputs, apply=apply, today=today)
    wf_result = wf.run(vault=vault, config=config, trace=trace)
    return _to_archive_result(wf_result, vault=vault, apply=apply)


def _to_archive_result(wf: WorkflowResult, *, vault: Path, apply: bool) -> ArchiveResult:
    plan = ArchivePlan()
    moved = False

    for step in wf.steps:
        if step.name == "resolve_target" and isinstance(step.output, dict):
            plan.source = step.output.get("source")
        elif step.name == "scan_open_tasks" and isinstance(step.output, dict):
            plan.open_tasks = list(step.output.get("tasks") or [])
        elif step.name == "compose_archive" and isinstance(step.output, dict):
            plan.destination = step.output.get("destination")
            plan.tasks_cancelled = int(step.output.get("tasks_cancelled") or 0)
            plan.outcome_action = str(step.output.get("outcome_action") or "none")
            plan.frontmatter_migrated = bool(step.output.get("frontmatter_migrated"))
        elif step.name == "write_and_move" and isinstance(step.output, dict):
            moved = bool(step.output.get("moved"))

    return ArchiveResult(
        vault=str(vault),
        apply=apply,
        ok=wf.ok,
        plan=plan,
        moved=moved,
        escalation=wf.escalation,
        error=wf.error,
        run_id=wf.run_id,
    )

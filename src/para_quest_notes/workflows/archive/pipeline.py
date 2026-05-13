"""Pipeline assembly for ``pqn-archive``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.prompts import PromptLoader
from para_quest_notes.adapter.step import Workflow, WorkflowResult
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.workflows.archive.contract import (
    ArchiveInputs,
    ArchivePlan,
    ArchiveResult,
)
from para_quest_notes.workflows.archive.steps.compose_archive import ComposeArchive
from para_quest_notes.workflows.archive.steps.decide_task_action import DecideTaskAction
from para_quest_notes.workflows.archive.steps.generate_outcome import GenerateOutcome
from para_quest_notes.workflows.archive.steps.prepare_outcome import PrepareOutcome
from para_quest_notes.workflows.archive.steps.resolve_target import ResolveTarget
from para_quest_notes.workflows.archive.steps.scan_open_tasks import ScanOpenTasks
from para_quest_notes.workflows.archive.steps.validate_after import ValidateAfter
from para_quest_notes.workflows.archive.steps.verify_project import VerifyProject
from para_quest_notes.workflows.archive.steps.write_and_move import WriteAndMove

PROMPTS_DIR = Path(__file__).parent / "prompts"


def build_workflow(
    inputs: ArchiveInputs,
    *,
    apply: bool,
    today: str | None = None,
    model: str | None = None,
) -> Workflow:
    loader = PromptLoader(PROMPTS_DIR)
    return Workflow(
        name="archive",
        steps=[
            ResolveTarget(inputs.target),
            VerifyProject(),
            ScanOpenTasks(),
            DecideTaskAction(cancel_open_tasks=inputs.cancel_open_tasks),
            PrepareOutcome(
                outcome=inputs.outcome,
                generate_outcome=inputs.generate_outcome,
                apply=apply,
            ),
            GenerateOutcome(prompt=loader.get("generate_outcome"), model=model),
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
    llm: Any = None,
    model: str | None = None,
    config: Config | None = None,
    trace: TraceWriter | None = None,
    today: str | None = None,
) -> ArchiveResult:
    """Run the archive workflow once. Returns a structured result."""
    wf = build_workflow(inputs, apply=apply, today=today, model=model)
    wf_result = wf.run(vault=vault, config=config, llm=llm, trace=trace)
    return _to_archive_result(wf_result, vault=vault, apply=apply)


def _to_archive_result(wf: WorkflowResult, *, vault: Path, apply: bool) -> ArchiveResult:
    plan = ArchivePlan()
    moved = False

    for step in wf.steps:
        if step.name == "resolve_target" and isinstance(step.output, dict):
            plan.source = step.output.get("source")
        elif step.name == "scan_open_tasks" and isinstance(step.output, dict):
            plan.open_tasks = list(step.output.get("tasks") or [])
        elif step.name == "prepare_outcome" and isinstance(step.output, dict):
            plan.outcome_action = str(step.output.get("action") or plan.outcome_action)
        elif step.name == "generate_outcome" and isinstance(step.output, dict):
            if step.output.get("action") == "generated":
                plan.outcome_action = "generated"
                plan.outcome_text = step.output.get("outcome_text")
        elif step.name == "compose_archive" and isinstance(step.output, dict):
            plan.destination = step.output.get("destination")
            plan.tasks_cancelled = int(step.output.get("tasks_cancelled") or 0)
            plan.outcome_action = str(step.output.get("outcome_action") or "none")
            plan.frontmatter_migrated = bool(step.output.get("frontmatter_migrated"))
        elif step.name == "write_and_move" and isinstance(step.output, dict):
            moved = bool(step.output.get("moved"))

    if (
        wf.escalation
        and wf.escalation.get("step") == "prepare_outcome"
        and plan.outcome_action == "none"
    ):
        plan.outcome_action = "required"

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

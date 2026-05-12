"""Pipeline assembly for ``pqn-ingest``.

The pipeline runs once per inbox file. Vault-level Quest discovery is
done once by the caller (``ingest_inbox``) and seeded into each run's
scratchpad.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.prompts import PromptLoader
from para_quest_notes.adapter.step import Workflow, WorkflowResult
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.vault.quests import Quest, discover_quests
from para_quest_notes.workflows.ingest_inbox.contract import (
    AppliedChange,
    Decisions,
    FileResult,
    IngestResult,
)
from para_quest_notes.workflows.ingest_inbox.steps.apply_move import ApplyMove
from para_quest_notes.workflows.ingest_inbox.steps.classify_para import ClassifyPara
from para_quest_notes.workflows.ingest_inbox.steps.pick_quest import PickQuest
from para_quest_notes.workflows.ingest_inbox.steps.plan_destination import PlanDestination
from para_quest_notes.workflows.ingest_inbox.steps.propose_filename import ProposeFilename
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanNote

PROMPTS_DIR = Path(__file__).parent / "prompts"


def build_workflow(source: Path, *, apply: bool, model: str | None = None) -> Workflow:
    loader = PromptLoader(PROMPTS_DIR)
    return Workflow(
        name="ingest_inbox",
        steps=[
            ScanNote(source=source),
            ClassifyPara(prompt=loader.get("classify_para"), model=model),
            PickQuest(prompt=loader.get("pick_quest"), model=model),
            ProposeFilename(prompt=loader.get("propose_filename"), model=model),
            PlanDestination(),
            ApplyMove(apply=apply),
        ],
    )


def ingest_one(
    source: Path,
    *,
    vault: Path,
    llm: Any,
    apply: bool = False,
    model: str | None = None,
    config: Config | None = None,
    trace: TraceWriter | None = None,
    vault_quests: list[Quest] | None = None,
) -> FileResult:
    quests = vault_quests if vault_quests is not None else discover_quests(vault)
    wf = build_workflow(source, apply=apply, model=model)
    wf_result = wf.run(
        vault=vault,
        config=config,
        llm=llm,
        trace=trace,
        scratchpad={"vault_quests": quests},
    )
    return _to_file_result(source, vault, wf_result, apply=apply)


def ingest_inbox(
    vault: Path,
    *,
    llm: Any,
    apply: bool = False,
    model: str | None = None,
    config: Config | None = None,
    trace: TraceWriter | None = None,
    files: Iterable[Path] | None = None,
    run_id: str = "",
) -> IngestResult:
    inbox_dir = vault / "inbox"
    if files is not None:
        candidates = list(files)
    elif inbox_dir.is_dir():
        candidates = sorted(p for p in inbox_dir.glob("*.md") if p.is_file())
    else:
        candidates = []

    quests = discover_quests(vault)
    result = IngestResult(vault=str(vault), run_id=run_id, apply=apply)
    for src in candidates:
        result.files.append(
            ingest_one(
                src,
                vault=vault,
                llm=llm,
                apply=apply,
                model=model,
                config=config,
                trace=trace,
                vault_quests=quests,
            )
        )
    if not result.run_id and result.files:
        result.run_id = result.files[0].run_id or ""
    return result


def _to_file_result(source: Path, vault: Path, wf: WorkflowResult, *, apply: bool) -> FileResult:
    decisions = Decisions()
    change: AppliedChange | None = None

    for step in wf.steps:
        if step.name == "classify_para" and isinstance(step.output, dict):
            decisions.para_type = step.output.get("type")
        elif step.name == "pick_quest" and isinstance(step.output, dict):
            decisions.quests = list(step.output.get("quests") or [])
        elif step.name == "propose_filename" and isinstance(step.output, dict):
            decisions.filename = step.output.get("filename")
        elif step.name == "plan_destination" and isinstance(step.output, dict):
            decisions.destination = step.output.get("destination")
        elif step.name == "apply_move" and isinstance(step.output, AppliedChange):
            change = step.output

    fr = FileResult(
        source=str(source.relative_to(vault).as_posix()),
        ok=wf.ok,
        decisions=decisions,
        applied=apply and wf.ok and change is not None,
        change=change,
        escalation=wf.escalation,
        error=wf.error,
        run_id=wf.run_id,
    )
    return fr

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.prompts import PromptLoader
from para_quest_notes.eval.fixtures import Fixture, parse_ingest_fixture
from para_quest_notes.eval.judges import Verdict, judge_responds, judge_step
from para_quest_notes.eval.registry import (
    EvaluableStep,
    WorkflowEval,
    register_step,
    register_workflow,
)
from para_quest_notes.vault.frontmatter import ParsedNote
from para_quest_notes.vault.quests import Quest
from para_quest_notes.workflows.ingest_inbox.pipeline import PROMPTS_DIR
from para_quest_notes.workflows.ingest_inbox.steps.classify_para import ClassifyPara
from para_quest_notes.workflows.ingest_inbox.steps.pick_quest import PickQuest
from para_quest_notes.workflows.ingest_inbox.steps.plan_destination import PlanDestination
from para_quest_notes.workflows.ingest_inbox.steps.propose_filename import ProposeFilename
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanResult

WORKFLOW_NAME = "ingest"


def _build_scan(fixture: Fixture) -> ScanResult:
    parsed = ParsedNote(
        frontmatter=dict(fixture.frontmatter),
        body=fixture.body,
        had_frontmatter=bool(fixture.frontmatter),
    )
    # source_filename (when a fixture declares one) is the explicit inbox
    # basename propose_filename sees; otherwise derive it from the id.
    basename = fixture.source_filename or f"{fixture.id}.md"
    fake_source = Path("inbox") / basename
    return ScanResult(
        source=fake_source,
        parsed=parsed,
        attachments=[],
        title=fixture.title,
    )


def _scratchpad_for(fixture: Fixture, *, step: str) -> dict[str, Any]:
    scan = _build_scan(fixture)
    quests = [Quest(name=q.name, quest_kind=q.kind) for q in fixture.quest_catalog]
    pad: dict[str, Any] = {"scan": scan, "vault_quests": quests}
    expected = fixture.expected

    if step in ("pick_quest", "propose_filename", "plan_destination") and (
        expected.classify_para is not None
    ):
        pad["para_type"] = expected.classify_para.type
    if step == "plan_destination":
        if expected.plan_destination is not None:
            pad["filename"] = expected.plan_destination.destination.rsplit("/", 1)[-1]
        elif expected.propose_filename is not None:
            base = expected.propose_filename.canonical
            pad["filename"] = f"{base}.md" if not base.endswith(".md") else base
    return pad


def _build_classify_para(model: str | None) -> ClassifyPara:
    loader = PromptLoader(PROMPTS_DIR)
    return ClassifyPara(prompt=loader.get("classify_para"), model=model)


def _build_pick_quest(model: str | None) -> PickQuest:
    loader = PromptLoader(PROMPTS_DIR)
    return PickQuest(prompt=loader.get("pick_quest"), model=model)


def _build_propose_filename(model: str | None) -> ProposeFilename:
    loader = PromptLoader(PROMPTS_DIR)
    return ProposeFilename(prompt=loader.get("propose_filename"), model=model)


def _build_plan_destination(_: str | None) -> PlanDestination:
    return PlanDestination()


def _judge(step_name: str, actual: dict[str, Any] | None, fixture: Fixture) -> Verdict:
    return judge_step(step_name, actual, fixture.expected)


def _has_expected(step_name: str, fixture: Fixture) -> bool:
    return fixture.expected.has(step_name)


def _fake_response(step_name: str, fixture: Fixture) -> str:
    exp = fixture.expected
    if step_name == "classify_para" and exp.classify_para is not None:
        return json.dumps({"type": exp.classify_para.type, "confidence": 0.9, "reason": "fake"})
    if step_name == "pick_quest" and exp.pick_quest is not None:
        if exp.pick_quest.skipped:
            return json.dumps({"quests": [], "confidence": 0.9, "reason": "fake-skip"})
        first = next(iter(exp.pick_quest.acceptable))
        return json.dumps({"quests": sorted(first), "confidence": 0.9, "reason": "fake"})
    if step_name == "propose_filename" and exp.propose_filename is not None:
        title_words = [w.capitalize() for w in exp.propose_filename.canonical.split()]
        filename = (" ".join(title_words) or "Untitled") + ".md"
        return json.dumps({"choice": "generate", "filename": filename, "reason": "fake"})
    return "{}"


def register_ingest_evals() -> None:
    register_workflow(
        WorkflowEval(
            name=WORKFLOW_NAME,
            fixture_loader=parse_ingest_fixture,
        )
    )
    register_step(
        EvaluableStep(
            workflow=WORKFLOW_NAME,
            name="classify_para",
            step_factory=_build_classify_para,
            context_builder=lambda fixture: _scratchpad_for(fixture, step="classify_para"),
            judge=lambda actual, fixture: _judge("classify_para", actual, fixture),
            has_expectation=lambda fixture: _has_expected("classify_para", fixture),
            uses_llm=True,
            fake_response=lambda fixture: _fake_response("classify_para", fixture),
            responds_judge=judge_responds,
        )
    )
    register_step(
        EvaluableStep(
            workflow=WORKFLOW_NAME,
            name="pick_quest",
            step_factory=_build_pick_quest,
            context_builder=lambda fixture: _scratchpad_for(fixture, step="pick_quest"),
            judge=lambda actual, fixture: _judge("pick_quest", actual, fixture),
            has_expectation=lambda fixture: _has_expected("pick_quest", fixture),
            uses_llm=True,
            fake_response=lambda fixture: _fake_response("pick_quest", fixture),
            responds_judge=judge_responds,
        )
    )
    register_step(
        EvaluableStep(
            workflow=WORKFLOW_NAME,
            name="propose_filename",
            step_factory=_build_propose_filename,
            context_builder=lambda fixture: _scratchpad_for(fixture, step="propose_filename"),
            judge=lambda actual, fixture: _judge("propose_filename", actual, fixture),
            has_expectation=lambda fixture: _has_expected("propose_filename", fixture),
            uses_llm=True,
            fake_response=lambda fixture: _fake_response("propose_filename", fixture),
            responds_judge=judge_responds,
        )
    )
    register_step(
        EvaluableStep(
            workflow=WORKFLOW_NAME,
            name="plan_destination",
            step_factory=_build_plan_destination,
            context_builder=lambda fixture: _scratchpad_for(fixture, step="plan_destination"),
            judge=lambda actual, fixture: _judge("plan_destination", actual, fixture),
            has_expectation=lambda fixture: _has_expected("plan_destination", fixture),
            uses_llm=False,
            fake_response=None,
            responds_judge=None,
        )
    )


__all__ = ["WORKFLOW_NAME", "register_ingest_evals"]

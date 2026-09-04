from __future__ import annotations

import json
from pathlib import Path

from para_quest_notes.adapter.prompts import PromptLoader
from para_quest_notes.eval.fixtures import CreateFixture, parse_create_fixture
from para_quest_notes.eval.judges import Verdict, judge_responds, judge_template_merge
from para_quest_notes.eval.registry import (
    EvaluableStep,
    WorkflowEval,
    register_step,
    register_workflow,
)
from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.pipeline import PROMPTS_DIR
from para_quest_notes.workflows.create.steps.merge_template import MergeTemplate

WORKFLOW_NAME = "create"
_FIXED_TODAY = "2026-09-04"


def _scratchpad_for(fixture: CreateFixture) -> dict[str, object]:
    inputs = CreateInputs(
        title=fixture.title,
        type="project",
        supports=["[[Health]]"],
        body=fixture.stdin,
        template=fixture.template_name,
        merge_template=True,
    )
    return {"inputs": inputs, "title": fixture.title}


def _prepare_vault(fixture: CreateFixture, vault: Path) -> None:
    template_dir = (vault / "resources" / "templates").resolve()
    filename = (
        fixture.template_name
        if fixture.template_name.endswith(".md")
        else f"{fixture.template_name}.md"
    )
    template_path = (template_dir / filename).resolve()
    if not template_path.is_relative_to(template_dir):
        raise ValueError("create eval template path escaped the disposable vault")
    template_dir.mkdir(parents=True, exist_ok=True)
    template_path.write_text(fixture.template, encoding="utf-8")


def _build_merge_template(model: str | None) -> MergeTemplate:
    loader = PromptLoader(PROMPTS_DIR)
    return MergeTemplate(
        prompt=loader.get("merge_template"),
        today=_FIXED_TODAY,
        model=model,
    )


def _judge(actual: dict[str, object] | None, fixture: CreateFixture) -> Verdict:
    expected = fixture.expected.merge_template
    if expected is None:
        return Verdict(
            step="merge_template",
            ok=False,
            reason="fixture has no expected.merge_template",
        )
    return judge_template_merge(actual, expected)


def _fake_response(fixture: CreateFixture) -> str:
    expected = fixture.expected.merge_template
    if expected is None:
        return "{}"
    return json.dumps(
        {
            "placements": [
                {"block_id": block_id, "section_id": section_id}
                for block_id, section_id in expected.placements
            ]
        }
    )


def register_create_evals() -> None:
    register_workflow(
        WorkflowEval(
            name=WORKFLOW_NAME,
            fixture_loader=parse_create_fixture,
        )
    )
    register_step(
        EvaluableStep(
            workflow=WORKFLOW_NAME,
            name="merge_template",
            step_factory=_build_merge_template,
            context_builder=_scratchpad_for,
            judge=_judge,
            has_expectation=lambda fixture: fixture.expected.has("merge_template"),
            uses_llm=True,
            fake_response=_fake_response,
            responds_judge=judge_responds,
            prepare_vault=_prepare_vault,
        )
    )


__all__ = ["WORKFLOW_NAME", "register_create_evals"]

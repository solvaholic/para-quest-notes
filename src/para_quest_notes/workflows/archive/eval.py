from __future__ import annotations

from para_quest_notes.adapter.prompts import PromptLoader
from para_quest_notes.eval.fixtures import ArchiveFixture, parse_archive_fixture
from para_quest_notes.eval.judges import Verdict, judge_generate_outcome, judge_text_responds
from para_quest_notes.eval.registry import (
    EvaluableStep,
    WorkflowEval,
    register_step,
    register_workflow,
)
from para_quest_notes.vault.frontmatter import split_note
from para_quest_notes.workflows.archive.pipeline import PROMPTS_DIR
from para_quest_notes.workflows.archive.steps.generate_outcome import GenerateOutcome

WORKFLOW_NAME = "archive"


def _scratchpad_for(fixture: ArchiveFixture) -> dict[str, object]:
    return {
        "split": split_note(fixture.body),
        "source_rel": f"projects/{fixture.title}.md",
        "note_title": fixture.title,
        "needs_generate_outcome": True,
        "outcome_action": "none",
        "outcome_text": None,
        "completed_task_lines": list(fixture.completed_tasks),
        "inbound_links": [
            {"basename": link.basename, **({"snippet": link.snippet} if link.snippet else {})}
            for link in fixture.inbound_links
        ],
    }


def _build_generate_outcome(model: str | None) -> GenerateOutcome:
    loader = PromptLoader(PROMPTS_DIR)
    return GenerateOutcome(prompt=loader.get("generate_outcome"), model=model)


def _judge(actual: dict[str, object] | None, fixture: ArchiveFixture) -> Verdict:
    expected = fixture.expected.generate_outcome
    if expected is None:
        return Verdict(
            step="generate_outcome",
            ok=False,
            reason="fixture has no expected.generate_outcome",
        )
    return judge_generate_outcome(actual, expected)


def register_archive_evals() -> None:
    register_workflow(
        WorkflowEval(
            name=WORKFLOW_NAME,
            fixture_loader=parse_archive_fixture,
        )
    )
    register_step(
        EvaluableStep(
            workflow=WORKFLOW_NAME,
            name="generate_outcome",
            step_factory=_build_generate_outcome,
            context_builder=_scratchpad_for,
            judge=_judge,
            has_expectation=lambda fixture: fixture.expected.has("generate_outcome"),
            uses_llm=True,
            fake_response=lambda fixture: fixture.fake_response,
            responds_judge=judge_text_responds,
        )
    )


__all__ = ["WORKFLOW_NAME", "register_archive_evals"]

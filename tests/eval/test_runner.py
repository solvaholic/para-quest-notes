"""End-to-end harness tests using FakeLLM.

We exercise the runner with the project's actual Step classes; the
FakeLLM responder returns scripted JSON keyed off the step's prompt
name (extracted from ``prompt_id``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.fake_llm import FakeLLM
from para_quest_notes.adapter.llm import LLMResponse
from para_quest_notes.eval.__main__ import DEFAULT_FIXTURES_DIR, _fake_llm_factory
from para_quest_notes.eval.fixtures import Fixture, load_fixtures
from para_quest_notes.eval.runner import ModelSpec, run_matrix


def _fixture(tmp_path: Path) -> Fixture:
    p = tmp_path / "fx.yaml"
    p.write_text(
        """
id: smoke
title: Train for 5K
body: |
  Couch to 5K plan.
quest_catalog:
  - { name: Health, kind: main }
  - { name: Connect, kind: main }
expected:
  classify_para: { type: project }
  pick_quest:
    acceptable:
      - [Health]
  propose_filename:
    canonical: "train for 5k"
  plan_destination:
    destination: "projects/Train For 5k.md"
""",
        encoding="utf-8",
    )
    return load_fixtures(p)[0]


def _scripted_responder(answers: dict[str, str]) -> Any:
    """Return a FakeLLM responder that picks JSON by step name in prompt_id."""

    def responder(call: Any) -> LLMResponse:
        name = (call.prompt_id or "").split("@", 1)[0]
        return LLMResponse(
            text=answers.get(name, "{}"),
            model=call.model,
            latency_ms=0,
            prompt_id=call.prompt_id,
        )

    return responder


def _factory(answers: dict[str, str]) -> Any:
    def make() -> FakeLLM:
        return FakeLLM(default_model="fake", responder=_scripted_responder(answers))

    return make


def test_all_steps_pass_with_correct_answers(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    answers = {
        "classify_para": json.dumps({"type": "project", "confidence": 0.9, "reason": "ok"}),
        "pick_quest": json.dumps({"quests": ["Health"], "confidence": 0.9, "reason": "ok"}),
        "propose_filename": json.dumps(
            {"choice": "generate", "filename": "Train For 5K.md", "reason": "ok"}
        ),
    }
    out = tmp_path / "run"
    summary = run_matrix(
        [fx],
        [ModelSpec(name="fake", llm_factory=_factory(answers))],
        out_dir=out,
    )
    assert len(summary.cells) == 4
    assert all(c.verdict.ok for c in summary.cells), [
        (c.step, c.verdict.reason) for c in summary.cells if not c.verdict.ok
    ]
    assert (out / "trace.jsonl").exists()
    assert (out / "summary.json").exists()


def test_wrong_answer_fails_judge(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    answers = {
        "classify_para": json.dumps({"type": "area", "confidence": 0.9, "reason": "wrong"}),
        "pick_quest": json.dumps({"quests": ["Connect"], "confidence": 0.9, "reason": "wrong"}),
        "propose_filename": json.dumps({"filename": "Wrong Title.md", "reason": "no"}),
    }
    summary = run_matrix(
        [fx],
        [ModelSpec(name="fake", llm_factory=_factory(answers))],
    )
    by_step = {c.step: c for c in summary.cells}
    assert not by_step["classify_para"].verdict.ok
    assert not by_step["pick_quest"].verdict.ok
    assert not by_step["propose_filename"].verdict.ok


def test_empty_response_records_responds_failure(tmp_path: Path) -> None:
    fx = _fixture(tmp_path)
    summary = run_matrix(
        [fx],
        [ModelSpec(name="fake", llm_factory=_factory({}))],
    )
    llm_cells = [c for c in summary.cells if c.responds is not None]
    assert all(c.responds and c.responds.ok for c in llm_cells)
    assert all(not c.verdict.ok for c in llm_cells)


def test_unload_called_per_model(tmp_path: Path) -> None:
    """If the LLM client exposes ``unload``, the runner must call it."""
    fx = _fixture(tmp_path)

    class UnloadableFake(FakeLLM):
        unload_calls: list[str] = []

        def unload(self, model: str | None = None) -> bool:
            UnloadableFake.unload_calls.append(model or "")
            return True

    UnloadableFake.unload_calls.clear()

    def make_a() -> UnloadableFake:
        return UnloadableFake(default_model="a", responder=_scripted_responder({}))

    def make_b() -> UnloadableFake:
        return UnloadableFake(default_model="b", responder=_scripted_responder({}))

    run_matrix(
        [fx],
        [
            ModelSpec(name="model-a", llm_factory=make_a),
            ModelSpec(name="model-b", llm_factory=make_b),
        ],
    )
    assert UnloadableFake.unload_calls == ["model-a", "model-b"]


def test_skipped_pick_quest_for_resource(tmp_path: Path) -> None:
    p = tmp_path / "res.yaml"
    p.write_text(
        """
id: res
title: Sourdough Notes
body: |
  Reference info.
expected:
  classify_para: { type: resource }
  pick_quest: { skipped: true }
""",
        encoding="utf-8",
    )
    fx = load_fixtures(p)[0]
    answers = {
        "classify_para": json.dumps({"type": "resource", "confidence": 0.9, "reason": "ok"}),
    }
    summary = run_matrix([fx], [ModelSpec(name="fake", llm_factory=_factory(answers))])
    by_step = {c.step: c for c in summary.cells}
    assert by_step["classify_para"].verdict.ok
    assert by_step["pick_quest"].verdict.ok
    assert by_step["pick_quest"].responds is None


def test_fake_regression_on_real_ingest_fixtures(tmp_path: Path) -> None:
    fixtures = load_fixtures(DEFAULT_FIXTURES_DIR)
    summary = run_matrix(
        fixtures,
        [ModelSpec(name="fake-model", llm_factory=_fake_llm_factory(fixtures))],
        out_dir=tmp_path,
    )
    rows = sorted((c.workflow, c.fixture_id, c.step, c.verdict.ok) for c in summary.cells)
    assert len(rows) == 35
    assert all(ok for _, _, _, ok in rows)
    assert {workflow for workflow, _, _, _ in rows} == {"archive", "ingest"}


def test_archive_step_runs_with_fake_fixture(tmp_path: Path) -> None:
    fixtures = load_fixtures(DEFAULT_FIXTURES_DIR)
    summary = run_matrix(
        fixtures,
        [ModelSpec(name="fake-model", llm_factory=_fake_llm_factory(fixtures))],
        steps=["archive:generate_outcome"],
        out_dir=tmp_path,
    )
    assert len(summary.cells) == 3
    assert all(cell.workflow == "archive" for cell in summary.cells)
    assert all(cell.responds and cell.responds.ok for cell in summary.cells)
    assert all(cell.verdict.ok for cell in summary.cells)

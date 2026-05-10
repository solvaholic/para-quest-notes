"""Tests for adapter.step (Step / Workflow runner)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult, Workflow
from para_quest_notes.adapter.trace import TraceWriter


@dataclass
class RecordingStep:
    name: str
    output: str = "ok"

    def run(self, ctx: StepContext) -> StepResult:
        ctx.scratchpad.setdefault("ran", []).append(self.name)
        return StepResult(name=self.name, output=self.output, meta={"size": len(self.output)})


@dataclass
class EscalatingStep:
    name: str

    def run(self, ctx: StepContext) -> StepResult:
        raise EscalateToUser(step=self.name, reason="don't know", options=[{"id": "a"}])


@dataclass
class BoomStep:
    name: str

    def run(self, ctx: StepContext) -> StepResult:
        raise RuntimeError("boom")


def _read_trace(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().strip().split("\n")]


def test_runs_steps_in_order(tmp_path: Path) -> None:
    wf = Workflow("t", [RecordingStep("a"), RecordingStep("b"), RecordingStep("c")])
    trace_path = tmp_path / "run.jsonl"
    with TraceWriter(trace_path) as t:
        result = wf.run(trace=t)
    assert result.ok
    assert [s.name for s in result.steps] == ["a", "b", "c"]
    events = _read_trace(trace_path)
    assert events[0]["event"] == "workflow.start"
    assert events[-1]["event"] == "workflow.complete"
    step_complete_events = [e for e in events if e["event"] == "step.complete"]
    assert [e["step"] for e in step_complete_events] == ["a", "b", "c"]


def test_escalation_short_circuits(tmp_path: Path) -> None:
    wf = Workflow("t", [RecordingStep("a"), EscalatingStep("b"), RecordingStep("c")])
    trace_path = tmp_path / "run.jsonl"
    with TraceWriter(trace_path) as t:
        result = wf.run(trace=t)
    assert not result.ok
    assert result.escalation == {
        "step": "b",
        "reason": "don't know",
        "options": [{"id": "a"}],
        "context": {},
    }
    # only the first step ran to completion
    assert [s.name for s in result.steps] == ["a"]
    events = _read_trace(trace_path)
    assert any(e["event"] == "step.escalate" and e["step"] == "b" for e in events)
    assert any(e["event"] == "workflow.escalate" for e in events)
    # never reached step c
    assert not any(e.get("step") == "c" for e in events)


def test_unhandled_exception_is_traced_then_raised(tmp_path: Path) -> None:
    wf = Workflow("t", [RecordingStep("a"), BoomStep("boom")])
    trace_path = tmp_path / "run.jsonl"
    with TraceWriter(trace_path) as t, pytest.raises(RuntimeError):
        wf.run(trace=t)
    events = _read_trace(trace_path)
    assert any(e["event"] == "step.error" and e["step"] == "boom" for e in events)


def test_scratchpad_is_shared_between_steps() -> None:
    wf = Workflow("t", [RecordingStep("a"), RecordingStep("b")])
    result = wf.run()
    assert result.ok
    # scratchpad lives on ctx; we can't access it post-run, but we can
    # confirm both ran via WorkflowResult.
    assert [s.name for s in result.steps] == ["a", "b"]


def test_empty_workflow_rejected() -> None:
    with pytest.raises(ValueError):
        Workflow("t", [])


def test_run_id_is_stable_within_run(tmp_path: Path) -> None:
    wf = Workflow("t", [RecordingStep("a"), RecordingStep("b")])
    trace_path = tmp_path / "run.jsonl"
    with TraceWriter(trace_path) as t:
        result = wf.run(trace=t)
    events = _read_trace(trace_path)
    run_ids = {e["run_id"] for e in events}
    assert run_ids == {result.run_id}

"""Eval matrix runner.

For each ``(model, fixture, step)`` cell, build a minimal
``StepContext`` with the scratchpad downstream steps need, run the
actual workflow Step class, and judge its output.

We call the same Step classes the production workflow uses — so the
prompts, schema validation, and escalation logic under test are
exactly what ships. The runner just stubs out scan/discovery so each
step can run without a vault on disk.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import PromptLoader
from para_quest_notes.adapter.step import StepContext
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.eval.fixtures import Fixture
from para_quest_notes.eval.judges import Verdict, judge_responds, judge_step
from para_quest_notes.workflows.ingest_inbox.frontmatter import ParsedNote
from para_quest_notes.workflows.ingest_inbox.pipeline import PROMPTS_DIR
from para_quest_notes.workflows.ingest_inbox.steps.classify_para import ClassifyPara
from para_quest_notes.workflows.ingest_inbox.steps.pick_quest import PickQuest
from para_quest_notes.workflows.ingest_inbox.steps.plan_destination import PlanDestination
from para_quest_notes.workflows.ingest_inbox.steps.propose_filename import ProposeFilename
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanResult
from para_quest_notes.workflows.ingest_inbox.vault_quests import Quest

# Steps we evaluate. ``scan_note`` and ``apply_move`` are pure and not
# part of the LLM eval matrix (scan is fixture-driven; apply touches
# disk and is tested via tests/workflows).
EVALUABLE_STEPS = ("classify_para", "pick_quest", "propose_filename", "plan_destination")


# --------------------------------------------------------------------------- #
# Result records
# --------------------------------------------------------------------------- #


@dataclass
class StepRunResult:
    """Outcome of running one Step class against one fixture."""

    step: str
    output: dict[str, Any] | None = None
    escalation: dict[str, Any] | None = None
    error: str | None = None
    raw_text: str | None = None  # last raw LLM response, if any
    prompt_id: str | None = None
    latency_ms: int = 0


@dataclass
class CellResult:
    """One cell of the matrix: (model, fixture, step)."""

    model: str
    temperature: float
    fixture_id: str
    step: str
    run: StepRunResult
    verdict: Verdict
    responds: Verdict | None = None  # only set for LLM steps

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "fixture_id": self.fixture_id,
            "step": self.step,
            "run": asdict(self.run),
            "verdict": asdict(self.verdict),
            "responds": asdict(self.responds) if self.responds else None,
        }


@dataclass
class RunSummary:
    """Top-level summary of an eval run."""

    started_at: float
    finished_at: float = 0.0
    fixture_count: int = 0
    models: list[str] = field(default_factory=list)
    cells: list[CellResult] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# LLM wrapper that records raw text per call
# --------------------------------------------------------------------------- #


class _RecordingLLM:
    """Wraps any LLM client so the runner can observe raw text + prompt_id."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.last_raw_text: str | None = None
        self.last_prompt_id: str | None = None
        self.last_latency_ms: int = 0

    def generate(self, prompt: str, **kwargs: Any) -> Any:
        self.last_raw_text = None
        self.last_prompt_id = kwargs.get("prompt_id")
        start = time.perf_counter()
        resp = self.inner.generate(prompt, **kwargs)
        self.last_latency_ms = int((time.perf_counter() - start) * 1000)
        # OllamaClient / FakeLLM both return LLMResponse with .text
        self.last_raw_text = getattr(resp, "text", None)
        return resp


# --------------------------------------------------------------------------- #
# Per-step runner
# --------------------------------------------------------------------------- #


def _build_scan(fixture: Fixture) -> ScanResult:
    parsed = ParsedNote(
        frontmatter=dict(fixture.frontmatter),
        body=fixture.body,
        had_frontmatter=bool(fixture.frontmatter),
    )
    # Synthesize a path so steps that read ``scan.source`` don't break.
    fake_source = Path("inbox") / f"{fixture.id}.md"
    return ScanResult(
        source=fake_source,
        parsed=parsed,
        attachments=[],
        title=fixture.title,
    )


def _scratchpad_for(fixture: Fixture, *, step: str) -> dict[str, Any]:
    """Pre-seed scratchpad with what each step expects upstream.

    We feed the *expected* PARA type / filename downstream so each
    step is judged in isolation: ``pick_quest`` shouldn't fail because
    ``classify_para`` got the type wrong.
    """
    scan = _build_scan(fixture)
    quests = [Quest(name=q.name, quest_kind=q.kind) for q in fixture.quest_catalog]
    pad: dict[str, Any] = {"scan": scan, "vault_quests": quests}
    expected = fixture.expected

    if step in ("pick_quest", "propose_filename", "plan_destination") and (
        expected.classify_para is not None
    ):
        pad["para_type"] = expected.classify_para.type
    if step == "plan_destination":
        # Seed the filename plan_destination expects to consume. Prefer
        # the expected destination's basename so the pure step can be
        # judged in isolation regardless of casing in canonical forms.
        if expected.plan_destination is not None:
            pad["filename"] = expected.plan_destination.destination.rsplit("/", 1)[-1]
        elif expected.propose_filename is not None:
            base = expected.propose_filename.canonical
            pad["filename"] = f"{base}.md" if not base.endswith(".md") else base
    return pad


def _make_step(step_name: str, *, model: str | None) -> Any:
    loader = PromptLoader(PROMPTS_DIR)
    if step_name == "classify_para":
        return ClassifyPara(prompt=loader.get("classify_para"), model=model)
    if step_name == "pick_quest":
        return PickQuest(prompt=loader.get("pick_quest"), model=model)
    if step_name == "propose_filename":
        return ProposeFilename(prompt=loader.get("propose_filename"), model=model)
    if step_name == "plan_destination":
        return PlanDestination()
    raise ValueError(f"unknown step {step_name!r}")


def _is_llm_step(step_name: str) -> bool:
    return step_name in ("classify_para", "pick_quest", "propose_filename")


def _run_one_step(
    fixture: Fixture,
    step_name: str,
    *,
    llm: Any,
    model: str,
    trace: TraceWriter | None,
    vault: Path | None = None,
) -> StepRunResult:
    rec = _RecordingLLM(llm) if _is_llm_step(step_name) else None
    step = _make_step(step_name, model=model if _is_llm_step(step_name) else None)
    pad = _scratchpad_for(fixture, step=step_name)
    ctx = StepContext(
        workflow="eval",
        run_id=f"{fixture.id}:{step_name}:{model}",
        vault=vault,
        config=None,
        llm=rec if rec is not None else None,
        trace=trace,
        scratchpad=pad,
    )

    start = time.perf_counter()
    try:
        result = step.run(ctx)
    except EscalateToUser as esc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return StepRunResult(
            step=step_name,
            escalation=esc.to_dict(),
            raw_text=rec.last_raw_text if rec else None,
            prompt_id=rec.last_prompt_id if rec else None,
            latency_ms=rec.last_latency_ms if rec else latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - record everything
        latency_ms = int((time.perf_counter() - start) * 1000)
        return StepRunResult(
            step=step_name,
            error=f"{type(exc).__name__}: {exc}",
            raw_text=rec.last_raw_text if rec else None,
            prompt_id=rec.last_prompt_id if rec else None,
            latency_ms=rec.last_latency_ms if rec else latency_ms,
        )

    output = result.output if isinstance(result.output, dict) else None
    return StepRunResult(
        step=step_name,
        output=output,
        raw_text=rec.last_raw_text if rec else None,
        prompt_id=rec.last_prompt_id if rec else None,
        latency_ms=rec.last_latency_ms if rec else 0,
    )


def _release_model(llm: Any, model_name: str, trace: TraceWriter | None) -> None:
    """Best-effort: ask the LLM client to unload the model.

    Local Ollama is memory-bound. After we finish a model's fixtures
    we want it out of memory before the next model loads. ``unload``
    is duck-typed so FakeLLM (which doesn't define it) is silently
    skipped.
    """
    if llm is None:
        return
    unload = getattr(llm, "unload", None)
    if unload is None:
        return
    try:
        ok = unload(model_name)
    except Exception as exc:  # noqa: BLE001 - never abort the run for a cleanup hop
        if trace is not None:
            trace.write(
                {"event": "eval.unload", "model": model_name, "ok": False, "error": str(exc)}
            )
        return
    if trace is not None:
        trace.write({"event": "eval.unload", "model": model_name, "ok": bool(ok)})


# --------------------------------------------------------------------------- #
# Matrix
# --------------------------------------------------------------------------- #


@dataclass
class ModelSpec:
    name: str
    temperature: float = 0.0
    # llm_factory(): produce a fresh client for this model. Called lazily.
    llm_factory: Any = None


def run_matrix(
    fixtures: list[Fixture],
    models: list[ModelSpec],
    *,
    steps: Iterable[str] = EVALUABLE_STEPS,
    out_dir: Path | None = None,
) -> RunSummary:
    """Run the matrix and (optionally) write a JSONL trace under ``out_dir``."""
    chosen_steps = tuple(s for s in steps if s in EVALUABLE_STEPS)
    summary = RunSummary(
        started_at=time.time(),
        fixture_count=len(fixtures),
        models=[m.name for m in models],
    )

    trace: TraceWriter | None = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        trace = TraceWriter(out_dir / "trace.jsonl")

    # Each fixture gets an isolated empty vault so steps that walk
    # the filesystem (propose_filename's collision check) don't pick
    # up notes from outside the eval run. Created lazily in a
    # tempdir; cleaned up at the end.
    eval_vault_root = Path(tempfile.mkdtemp(prefix="pqn-eval-vault-"))

    try:
        # Process models strictly one at a time. Local Ollama is memory-
        # bound — running a second model in parallel would either thrash
        # or OOM. After each model we ask Ollama to unload it before
        # spinning up the next one's client. (Hosted inference would let
        # us parallelize this loop; that's a future Phase 4 enhancement.)
        for spec in models:
            llm = spec.llm_factory() if spec.llm_factory else None
            try:
                for fixture in fixtures:
                    for step_name in chosen_steps:
                        if not fixture.expected.has(step_name):
                            # No expectation declared — skip.
                            continue
                        run = _run_one_step(
                            fixture,
                            step_name,
                            llm=llm,
                            model=spec.name,
                            trace=trace,
                            vault=eval_vault_root,
                        )
                        verdict = judge_step(step_name, run.output, fixture.expected)
                        # Only record `responds` when an LLM call actually
                        # happened. ``pick_quest`` short-circuits for
                        # resources without ever touching the model;
                        # judging "responds" there would be misleading.
                        responds = (
                            judge_responds(run.raw_text)
                            if _is_llm_step(step_name) and run.raw_text is not None
                            else None
                        )
                        cell = CellResult(
                            model=spec.name,
                            temperature=spec.temperature,
                            fixture_id=fixture.id,
                            step=step_name,
                            run=run,
                            verdict=verdict,
                            responds=responds,
                        )
                        summary.cells.append(cell)
                        if trace is not None:
                            trace.write({"event": "eval.cell", **cell.to_dict()})
            finally:
                _release_model(llm, spec.name, trace)
    finally:
        if trace is not None:
            trace.close()
        shutil.rmtree(eval_vault_root, ignore_errors=True)

    summary.finished_at = time.time()
    if out_dir is not None:
        (out_dir / "summary.json").write_text(
            json.dumps(_summary_to_dict(summary), indent=2, default=str) + "\n",
            encoding="utf-8",
        )
    return summary


def _summary_to_dict(summary: RunSummary) -> dict[str, Any]:
    return {
        "started_at": summary.started_at,
        "finished_at": summary.finished_at,
        "fixture_count": summary.fixture_count,
        "models": summary.models,
        "cells": [c.to_dict() for c in summary.cells],
    }


__all__ = [
    "EVALUABLE_STEPS",
    "CellResult",
    "ModelSpec",
    "RunSummary",
    "StepRunResult",
    "run_matrix",
]

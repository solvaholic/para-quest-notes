"""Eval matrix runner.

For each ``(model, fixture, step)`` cell, build a minimal
``StepContext`` with the scratchpad downstream steps need, run the
actual workflow Step class, and judge its output.

We call the same Step classes the production workflow uses - so the
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
from para_quest_notes.adapter.step import StepContext
from para_quest_notes.adapter.trace import TraceWriter
from para_quest_notes.eval.judges import Verdict
from para_quest_notes.eval.registry import (
    DEFAULT_WORKFLOW,
    EvaluableStep,
    get_evaluable_step,
    iter_evaluable_steps,
    parse_step_ref,
    register_defaults,
)


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
    workflow: str = DEFAULT_WORKFLOW

    def to_dict(self) -> dict[str, Any]:
        data = {
            "model": self.model,
            "temperature": self.temperature,
            "fixture_id": self.fixture_id,
            "step": self.step,
            "run": asdict(self.run),
            "verdict": asdict(self.verdict),
            "responds": asdict(self.responds) if self.responds else None,
        }
        if self.workflow != DEFAULT_WORKFLOW:
            data["workflow"] = self.workflow
        return data


@dataclass
class RunSummary:
    """Top-level summary of an eval run."""

    started_at: float
    finished_at: float = 0.0
    fixture_count: int = 0
    models: list[str] = field(default_factory=list)
    cells: list[CellResult] = field(default_factory=list)


class _RecordingLLM:
    """Wraps any LLM client so the runner can observe raw text + prompt_id."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.last_raw_text: str | None = None
        self.last_prompt_id: str | None = None
        self.last_latency_ms: int = 0

    def generate(self, prompt: str, **kwargs: Any) -> Any:
        return self._record("generate", prompt, **kwargs)

    def generate_text(self, prompt: str, **kwargs: Any) -> Any:
        return self._record("generate_text", prompt, **kwargs)

    def _record(self, method_name: str, prompt: str, **kwargs: Any) -> Any:
        self.last_raw_text = None
        self.last_prompt_id = kwargs.get("prompt_id")
        start = time.perf_counter()
        resp = getattr(self.inner, method_name)(prompt, **kwargs)
        self.last_latency_ms = int((time.perf_counter() - start) * 1000)
        self.last_raw_text = getattr(resp, "text", None)
        return resp


def _run_one_step(
    fixture: Any,
    step_spec: EvaluableStep,
    *,
    llm: Any,
    model: str,
    trace: TraceWriter | None,
    vault: Path | None = None,
) -> StepRunResult:
    if step_spec.prepare_vault is not None:
        if vault is None:
            raise ValueError(f"eval step {step_spec.ref} requires a disposable vault")
        step_spec.prepare_vault(fixture, vault)

    if step_spec.uses_llm:
        bind_fixture = getattr(llm, "bind_fixture", None)
        if callable(bind_fixture):
            bind_fixture(fixture)
    rec = _RecordingLLM(llm) if step_spec.uses_llm else None
    step = step_spec.step_factory(model if step_spec.uses_llm else None)
    ctx = StepContext(
        workflow="eval",
        run_id=f"{fixture.id}:{step_spec.name}:{model}",
        vault=vault,
        config=None,
        llm=rec if rec is not None else None,
        trace=trace,
        scratchpad=step_spec.context_builder(fixture),
    )

    start = time.perf_counter()
    try:
        result = step.run(ctx)
    except EscalateToUser as esc:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return StepRunResult(
            step=step_spec.name,
            escalation=esc.to_dict(),
            raw_text=rec.last_raw_text if rec else None,
            prompt_id=rec.last_prompt_id if rec else None,
            latency_ms=rec.last_latency_ms if rec else latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - record everything
        latency_ms = int((time.perf_counter() - start) * 1000)
        return StepRunResult(
            step=step_spec.name,
            error=f"{type(exc).__name__}: {exc}",
            raw_text=rec.last_raw_text if rec else None,
            prompt_id=rec.last_prompt_id if rec else None,
            latency_ms=rec.last_latency_ms if rec else latency_ms,
        )

    output = result.output if isinstance(result.output, dict) else None
    return StepRunResult(
        step=step_spec.name,
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


@dataclass
class ModelSpec:
    name: str
    temperature: float = 0.0
    llm_factory: Any = None


def run_matrix(
    fixtures: list[Any],
    models: list[ModelSpec],
    *,
    steps: Iterable[str] | None = None,
    out_dir: Path | None = None,
) -> RunSummary:
    """Run the matrix and (optionally) write a JSONL trace under ``out_dir``."""
    register_defaults()
    chosen_refs = tuple(parse_step_ref(step) for step in steps) if steps is not None else None
    summary = RunSummary(
        started_at=time.time(),
        fixture_count=len(fixtures),
        models=[m.name for m in models],
    )

    trace: TraceWriter | None = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        trace = TraceWriter(out_dir / "trace.jsonl")

    eval_vault_root = Path(tempfile.mkdtemp(prefix="pqn-eval-vault-"))

    try:
        for spec in models:
            llm = spec.llm_factory() if spec.llm_factory else None
            try:
                for fixture in fixtures:
                    workflow = getattr(fixture, "workflow", DEFAULT_WORKFLOW)
                    if chosen_refs is None:
                        step_specs = iter_evaluable_steps(workflow)
                    else:
                        step_specs = tuple(
                            get_evaluable_step(sel_workflow, sel_name)
                            for sel_workflow, sel_name in chosen_refs
                            if sel_workflow == workflow
                        )
                    for step_spec in step_specs:
                        if not step_spec.has_expectation(fixture):
                            continue
                        run = _run_one_step(
                            fixture,
                            step_spec,
                            llm=llm,
                            model=spec.name,
                            trace=trace,
                            vault=eval_vault_root,
                        )
                        responds = (
                            step_spec.responds_judge(run.raw_text)
                            if step_spec.responds_judge is not None and run.raw_text is not None
                            else None
                        )
                        cell = CellResult(
                            model=spec.name,
                            temperature=spec.temperature,
                            fixture_id=fixture.id,
                            workflow=workflow,
                            step=step_spec.name,
                            run=run,
                            verdict=step_spec.judge(run.output, fixture),
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
    "CellResult",
    "ModelSpec",
    "RunSummary",
    "StepRunResult",
    "run_matrix",
]

"""Step / Workflow primitives.

A ``Workflow`` is an ordered list of ``Step`` objects. Each step receives a
``StepContext`` (vault path, config, llm, trace writer, scratchpad shared
across steps) and returns a ``StepResult``.

When a step decides the rules don't fit, it raises ``EscalateToUser``. The
runner catches it, records a structured trace event, and stops. The CLI
surfaces the escalation payload as JSON - that's the contract agents
(Phase 7) and humans both consume.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.trace import TraceWriter


@dataclass
class StepContext:
    """Shared state passed to every step."""

    workflow: str
    run_id: str
    vault: Path | None = None
    config: Config | None = None
    llm: Any = None  # OllamaClient or FakeLLM; duck typing.
    trace: TraceWriter | None = None
    scratchpad: dict[str, Any] = field(default_factory=dict)

    def emit(self, event: dict[str, Any]) -> None:
        if self.trace is not None:
            self.trace.write({"run_id": self.run_id, "workflow": self.workflow, **event})


@dataclass
class StepResult:
    name: str
    ok: bool = True
    output: Any = None
    meta: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Step(Protocol):
    name: str

    def run(self, ctx: StepContext) -> StepResult: ...


@dataclass
class WorkflowResult:
    workflow: str
    run_id: str
    steps: list[StepResult] = field(default_factory=list)
    escalation: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.escalation is None and self.error is None and all(s.ok for s in self.steps)


class Workflow:
    """Ordered runner. No retries, no skipping - the steps decide that."""

    def __init__(self, name: str, steps: list[Step]):
        if not steps:
            raise ValueError("workflow must have at least one step")
        self.name = name
        self.steps = steps

    def run(
        self,
        *,
        vault: Path | None = None,
        config: Config | None = None,
        llm: Any = None,
        trace: TraceWriter | None = None,
        scratchpad: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        run_id = uuid.uuid4().hex[:12]
        ctx = StepContext(
            workflow=self.name,
            run_id=run_id,
            vault=vault,
            config=config,
            llm=llm,
            trace=trace,
            scratchpad=dict(scratchpad or {}),
        )
        result = WorkflowResult(workflow=self.name, run_id=run_id)
        ctx.emit({"event": "workflow.start", "steps": [s.name for s in self.steps]})

        for step in self.steps:
            start = time.perf_counter()
            try:
                step_result = step.run(ctx)
            except EscalateToUser as esc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                result.escalation = esc.to_dict()
                ctx.emit(
                    {
                        "event": "step.escalate",
                        "step": step.name,
                        "latency_ms": latency_ms,
                        "escalation": esc.to_dict(),
                    }
                )
                ctx.emit({"event": "workflow.escalate", "step": step.name})
                return result
            except Exception as exc:  # noqa: BLE001 - record everything, then re-raise
                latency_ms = int((time.perf_counter() - start) * 1000)
                result.error = f"{type(exc).__name__}: {exc}"
                ctx.emit(
                    {
                        "event": "step.error",
                        "step": step.name,
                        "latency_ms": latency_ms,
                        "error": result.error,
                    }
                )
                ctx.emit({"event": "workflow.error", "step": step.name})
                raise

            latency_ms = int((time.perf_counter() - start) * 1000)
            result.steps.append(step_result)
            ctx.emit(
                {
                    "event": "step.complete",
                    "step": step.name,
                    "ok": step_result.ok,
                    "latency_ms": latency_ms,
                    "meta": step_result.meta,
                }
            )

        ctx.emit({"event": "workflow.complete", "ok": result.ok})
        return result

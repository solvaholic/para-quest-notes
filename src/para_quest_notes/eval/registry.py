from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from para_quest_notes.eval.judges import Verdict

DEFAULT_WORKFLOW = "ingest"

FixtureLoader = Callable[[dict[str, Any], Path], Any]
StepFactory = Callable[[str | None], Any]
ContextBuilder = Callable[[Any], dict[str, Any]]
StepJudge = Callable[[dict[str, Any] | None, Any], "Verdict"]
HasExpectation = Callable[[Any], bool]
FakeResponseBuilder = Callable[[Any], str]
RespondsJudge = Callable[[str | None], "Verdict"]


@dataclass(frozen=True)
class WorkflowEval:
    name: str
    fixture_loader: FixtureLoader


@dataclass(frozen=True)
class EvaluableStep:
    workflow: str
    name: str
    step_factory: StepFactory
    context_builder: ContextBuilder
    judge: StepJudge
    has_expectation: HasExpectation
    uses_llm: bool
    fake_response: FakeResponseBuilder | None = None
    responds_judge: RespondsJudge | None = None

    @property
    def ref(self) -> str:
        return f"{self.workflow}:{self.name}"


class EvalRegistry:
    def __init__(self) -> None:
        self._workflows: dict[str, WorkflowEval] = {}
        self._steps: dict[tuple[str, str], EvaluableStep] = {}

    def register_workflow(self, workflow: WorkflowEval) -> WorkflowEval:
        existing = self._workflows.get(workflow.name)
        if existing is not None:
            if existing != workflow:
                raise ValueError(f"workflow {workflow.name!r} already registered")
            return existing
        self._workflows[workflow.name] = workflow
        return workflow

    def register_step(self, step: EvaluableStep) -> EvaluableStep:
        key = (step.workflow, step.name)
        existing = self._steps.get(key)
        if existing is not None:
            if existing != step:
                raise ValueError(f"step {step.ref!r} already registered")
            return existing
        if step.workflow not in self._workflows:
            raise ValueError(f"workflow {step.workflow!r} must be registered before its steps")
        self._steps[key] = step
        return step

    def get_workflow(self, name: str) -> WorkflowEval:
        try:
            return self._workflows[name]
        except KeyError as exc:
            raise KeyError(f"unknown eval workflow {name!r}") from exc

    def get_step(self, workflow: str, name: str) -> EvaluableStep:
        try:
            return self._steps[(workflow, name)]
        except KeyError as exc:
            raise KeyError(f"unknown eval step {workflow}:{name}") from exc

    def iter_steps(self, workflow: str | None = None) -> tuple[EvaluableStep, ...]:
        if workflow is None:
            return tuple(self._steps.values())
        return tuple(step for step in self._steps.values() if step.workflow == workflow)

    def iter_step_refs(self, workflow: str | None = None) -> tuple[str, ...]:
        return tuple(step.ref for step in self.iter_steps(workflow))


REGISTRY = EvalRegistry()
_DEFAULTS_REGISTERED = False


def register_workflow(workflow: WorkflowEval) -> WorkflowEval:
    return REGISTRY.register_workflow(workflow)


def register_step(step: EvaluableStep) -> EvaluableStep:
    return REGISTRY.register_step(step)


def get_workflow_eval(name: str) -> WorkflowEval:
    return REGISTRY.get_workflow(name)


def get_evaluable_step(workflow: str, name: str) -> EvaluableStep:
    return REGISTRY.get_step(workflow, name)


def iter_evaluable_steps(workflow: str | None = None) -> tuple[EvaluableStep, ...]:
    return REGISTRY.iter_steps(workflow)


def iter_step_refs(workflow: str | None = None) -> tuple[str, ...]:
    return REGISTRY.iter_step_refs(workflow)


def parse_step_ref(selector: str, *, default_workflow: str = DEFAULT_WORKFLOW) -> tuple[str, str]:
    value = selector.strip()
    if not value:
        raise ValueError("step selector must not be empty")
    if ":" in value:
        workflow, name = value.split(":", 1)
    else:
        workflow, name = default_workflow, value
    workflow = workflow.strip()
    name = name.strip()
    if not workflow or not name:
        raise ValueError(f"invalid step selector {selector!r}")
    return workflow, name


def format_step_ref(workflow: str, name: str, *, include_default: bool = False) -> str:
    if workflow == DEFAULT_WORKFLOW and not include_default:
        return name
    return f"{workflow}:{name}"


def register_defaults() -> None:
    global _DEFAULTS_REGISTERED
    if _DEFAULTS_REGISTERED:
        return
    from para_quest_notes.workflows.archive.eval import register_archive_evals
    from para_quest_notes.workflows.ingest_inbox.eval import register_ingest_evals

    register_ingest_evals()
    register_archive_evals()
    _DEFAULTS_REGISTERED = True


__all__ = [
    "DEFAULT_WORKFLOW",
    "EvaluableStep",
    "EvalRegistry",
    "REGISTRY",
    "WorkflowEval",
    "format_step_ref",
    "get_evaluable_step",
    "get_workflow_eval",
    "iter_evaluable_steps",
    "iter_step_refs",
    "parse_step_ref",
    "register_defaults",
    "register_step",
    "register_workflow",
]

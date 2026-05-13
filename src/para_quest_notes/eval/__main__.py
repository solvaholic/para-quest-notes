"""``python -m para_quest_notes.eval``: run the eval matrix.

Maintainer-facing entry point. Reads fixtures, runs each enabled step
across the model matrix, writes ``report.md`` + ``rows.csv`` + a JSONL
trace under ``--out``.

Two LLM modes:

* ``--fake`` (default for CI / dogfooding): a FakeLLM that returns the
  fixture's expected step response. Verifies the harness end-to-end
  without touching Ollama.
* Without ``--fake``: spins up :class:`OllamaClient` for each model.

The CLI never imports Ollama unless a real model is asked for; nothing
network-y runs by default.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.fake_llm import FakeLLM
from para_quest_notes.adapter.llm import LLMResponse
from para_quest_notes.eval.fixtures import load_fixtures
from para_quest_notes.eval.registry import (
    format_step_ref,
    get_evaluable_step,
    iter_evaluable_steps,
    parse_step_ref,
    register_defaults,
)
from para_quest_notes.eval.report import write_report
from para_quest_notes.eval.runner import ModelSpec, run_matrix

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "eval" / "fixtures"
DEFAULT_OUT_BASE = Path(__file__).resolve().parents[3] / "eval" / "runs"


# --------------------------------------------------------------------------- #
# Fake LLM that knows each fixture's expected answer per step.
# --------------------------------------------------------------------------- #


def _expected_response_for(fixture: Any, prompt_id: str | None) -> str:
    """Return text the step's parser will accept for this fixture/step."""
    name = (prompt_id or "").split("@", 1)[0]
    workflow = getattr(fixture, "workflow", "ingest")
    try:
        step = get_evaluable_step(workflow, name)
    except KeyError:
        return "{}"
    if step.fake_response is None:
        return "{}"
    return step.fake_response(fixture)


def _fixture_markers(fixture: Any) -> tuple[str, ...]:
    markers: list[str] = []
    title = getattr(fixture, "title", "")
    body = getattr(fixture, "body", "")
    if isinstance(title, str) and title.strip():
        markers.append(title.strip())
    if isinstance(body, str):
        preview = body.strip().splitlines()
        if preview:
            markers.append(preview[0][:120])
    return tuple(marker for marker in markers if marker)


def _fake_llm_factory(fixtures: list[Any]) -> Any:
    """Build a FakeLLM whose responder finds the matching fixture by prompt text."""
    by_marker_sorted = sorted(
        ((marker, fixture) for fixture in fixtures for marker in _fixture_markers(fixture)),
        key=lambda pair: -len(pair[0]),
    )

    def factory() -> FakeLLM:
        def responder(call: Any) -> LLMResponse:
            fixture: Any | None = None
            for marker, fx in by_marker_sorted:
                if marker and marker in call.prompt:
                    fixture = fx
                    break
            text = _expected_response_for(fixture, call.prompt_id) if fixture else "{}"
            return LLMResponse(
                text=text,
                model=call.model,
                latency_ms=0,
                prompt_id=call.prompt_id,
            )

        return FakeLLM(default_model="fake-model", responder=responder)

    return factory


# --------------------------------------------------------------------------- #
# Real Ollama (lazy import).
# --------------------------------------------------------------------------- #


def _ollama_factory(model_name: str, base_url: str, timeout: int) -> Any:
    from para_quest_notes.adapter.llm import OllamaClient

    def factory() -> OllamaClient:
        return OllamaClient(
            base_url=base_url,
            default_model=model_name,
            timeout_seconds=timeout,
        )

    return factory


# --------------------------------------------------------------------------- #
# CLI plumbing
# --------------------------------------------------------------------------- #


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m para_quest_notes.eval",
        description="Run the per-step eval harness for registered workflows.",
    )
    p.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES_DIR,
        help=f"fixture file or directory (default: {DEFAULT_FIXTURES_DIR})",
    )
    p.add_argument(
        "--models",
        type=str,
        default="",
        help="comma-separated model names (real Ollama). Ignored if --fake.",
    )
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument(
        "--steps",
        type=str,
        default="",
        help=(
            "comma-separated step names or workflow:step refs "
            "(default: all registered steps for each fixture workflow)"
        ),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help=("output directory; defaults to <repo>/eval/runs/<timestamp>/"),
    )
    p.add_argument(
        "--fake",
        action="store_true",
        help="use FakeLLM seeded from each fixture's expected output (CI-safe)",
    )
    p.add_argument("--ollama-base-url", type=str, default="http://localhost:11434")
    p.add_argument("--ollama-timeout", type=int, default=120)
    return p


def _valid_step_names() -> list[str]:
    register_defaults()
    return [format_step_ref(step.workflow, step.name) for step in iter_evaluable_steps()]


def _parse_steps(arg: str) -> list[str] | None:
    register_defaults()
    items = [s.strip() for s in arg.split(",") if s.strip()]
    if not items:
        return None
    bad: list[str] = []
    normalized: list[str] = []
    for item in items:
        try:
            workflow, name = parse_step_ref(item)
            get_evaluable_step(workflow, name)
        except (KeyError, ValueError):
            bad.append(item)
            continue
        normalized.append(f"{workflow}:{name}")
    if bad:
        raise SystemExit(f"unknown step(s): {bad}; valid: {_valid_step_names()}")
    return normalized


def _resolve_out(arg: Path | None) -> Path:
    if arg is not None:
        return arg
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_OUT_BASE / ts


def _build_models(args: argparse.Namespace, fixtures: list[Any]) -> list[ModelSpec]:
    if args.fake:
        factory = _fake_llm_factory(fixtures)
        return [ModelSpec(name="fake-model", temperature=args.temperature, llm_factory=factory)]
    names = [n.strip() for n in args.models.split(",") if n.strip()]
    if not names:
        raise SystemExit(
            "no models given. Pass --models name1,name2,... or --fake for CI-safe runs."
        )
    return [
        ModelSpec(
            name=name,
            temperature=args.temperature,
            llm_factory=_ollama_factory(name, args.ollama_base_url, args.ollama_timeout),
        )
        for name in names
    ]


def main(argv: Iterable[str] | None = None) -> int:
    register_defaults()
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    fixtures = load_fixtures(args.fixtures)
    if not fixtures:
        print(f"no fixtures found under {args.fixtures}", file=sys.stderr)
        return 2

    steps = _parse_steps(args.steps)
    models = _build_models(args, fixtures)
    out_dir = _resolve_out(args.out)

    summary = run_matrix(fixtures, models, steps=steps, out_dir=out_dir)
    report_path = write_report(summary, out_dir)

    total = len(summary.cells)
    passed = sum(1 for c in summary.cells if c.verdict.ok)
    print(f"eval: {passed}/{total} cells passed -> {report_path}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

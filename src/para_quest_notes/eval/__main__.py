"""``python -m para_quest_notes.eval``: run the eval matrix.

Maintainer-facing entry point. Reads fixtures, runs each enabled step
across the model matrix, writes ``report.md`` + ``rows.csv`` + a JSONL
trace under ``--out``.

Two LLM modes:

* ``--fake`` (default for CI / dogfooding): a FakeLLM that returns the
  fixture's expected JSON for each step. Useful for verifying the
  harness end-to-end without Ollama.
* Without ``--fake``: spins up :class:`OllamaClient` for each model.

The CLI never imports Ollama unless a real model is asked for; nothing
network-y runs by default.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.fake_llm import FakeLLM
from para_quest_notes.adapter.llm import LLMResponse
from para_quest_notes.eval.fixtures import Fixture, load_fixtures
from para_quest_notes.eval.report import write_report
from para_quest_notes.eval.runner import EVALUABLE_STEPS, ModelSpec, run_matrix

DEFAULT_FIXTURES_DIR = Path(__file__).resolve().parents[3] / "eval" / "fixtures"
DEFAULT_OUT_BASE = Path(__file__).resolve().parents[3] / "eval" / "runs"


# --------------------------------------------------------------------------- #
# Fake LLM that knows each fixture's expected answer per step.
# --------------------------------------------------------------------------- #


def _expected_json_for(fixture: Fixture, prompt_id: str | None) -> str:
    """Return JSON the LLM step's parser will accept for this fixture/step.

    We key off the prompt name embedded in ``prompt_id`` (e.g.
    ``"classify_para@<hash>"``) so the FakeLLM can serve all three
    LLM steps in a single matrix.
    """
    name = (prompt_id or "").split("@", 1)[0]
    exp = fixture.expected
    if name == "classify_para" and exp.classify_para is not None:
        return json.dumps({"type": exp.classify_para.type, "confidence": 0.9, "reason": "fake"})
    if name == "pick_quest" and exp.pick_quest is not None:
        if exp.pick_quest.skipped:
            # The step short-circuits before calling the LLM, but be safe.
            return json.dumps({"quests": [], "confidence": 0.9, "reason": "fake-skip"})
        # Pick the first acceptable set.
        first = next(iter(exp.pick_quest.acceptable))
        return json.dumps({"quests": sorted(first), "confidence": 0.9, "reason": "fake"})
    if name == "propose_filename" and exp.propose_filename is not None:
        # Convert canonical form to a Title Case-ish .md name.
        title_words = [w.capitalize() for w in exp.propose_filename.canonical.split()]
        filename = (" ".join(title_words) or "Untitled") + ".md"
        return json.dumps({"filename": filename, "reason": "fake"})
    # Fall through: empty JSON object — the step will escalate, which is
    # legitimate signal in the report.
    return "{}"


def _fake_llm_factory(fixtures: list[Fixture]) -> Any:
    """Build a FakeLLM whose responder finds the matching fixture by id.

    The runner sets ``ctx.run_id = "<fixture_id>:<step>:<model>"`` and
    LLM step prompts include the fixture's title in their render
    variables. The cleanest way to thread the fixture identity in is
    via ``prompt_id`` plus a lookup keyed on title — but since prompts
    are rendered with the fixture's actual title, we can pass
    fixture-by-title.

    We try longer titles first so a generic short title (e.g.
    ``"notes"``) doesn't collide with substrings inside prompt
    templates (the propose_filename prompt has bad-example text like
    ``"sourdough-notes.md"``).
    """
    by_title_sorted = sorted(
        ((f.title, f) for f in fixtures),
        key=lambda pair: -len(pair[0]),
    )

    def factory() -> FakeLLM:
        def responder(call: Any) -> LLMResponse:
            # Find which fixture this prompt was rendered for.
            fixture: Fixture | None = None
            for title, fx in by_title_sorted:
                if title and title in call.prompt:
                    fixture = fx
                    break
            text = _expected_json_for(fixture, call.prompt_id) if fixture else "{}"
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
        description="Run the per-step eval harness for pqn-ingest.",
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
        default=",".join(EVALUABLE_STEPS),
        help=f"comma-separated step names (default: {','.join(EVALUABLE_STEPS)})",
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


def _parse_steps(arg: str) -> list[str]:
    items = [s.strip() for s in arg.split(",") if s.strip()]
    bad = [s for s in items if s not in EVALUABLE_STEPS]
    if bad:
        raise SystemExit(f"unknown step(s): {bad}; valid: {list(EVALUABLE_STEPS)}")
    return items


def _resolve_out(arg: Path | None) -> Path:
    if arg is not None:
        return arg
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_OUT_BASE / ts


def _build_models(args: argparse.Namespace, fixtures: list[Fixture]) -> list[ModelSpec]:
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
    # Non-zero exit if any cell failed; useful in CI.
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())

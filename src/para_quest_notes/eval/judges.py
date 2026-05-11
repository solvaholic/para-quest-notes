"""Per-step judges for the eval harness.

Each judge takes the workflow's actual output (or the escalation that
came back instead) plus the fixture's expected payload, and returns a
``Verdict``.

Verdicts roll up into the report. Keep judges deterministic and cheap.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from para_quest_notes.eval.fixtures import (
    Expected,
    ExpectedClassify,
    ExpectedDestination,
    ExpectedFilename,
    ExpectedPickQuest,
)


@dataclass
class Verdict:
    """Result of judging one (step, fixture) pair."""

    step: str
    ok: bool
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# `responds`: did the LLM produce parseable JSON at all?
# --------------------------------------------------------------------------- #


def judge_responds(raw_text: str | None) -> Verdict:
    """Cheap gate: parseable JSON object response, or not.

    Phase-0 baseline per PLAN.md risk note about empty `format=json`
    replies. Independent of semantic correctness.
    """
    if raw_text is None:
        return Verdict(step="responds", ok=False, reason="no LLM call recorded")
    text = raw_text.strip()
    if not text:
        return Verdict(step="responds", ok=False, reason="empty response")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        return Verdict(
            step="responds",
            ok=False,
            reason=f"unparseable JSON: {exc.msg}",
            detail={"raw_preview": text[:200]},
        )
    if not isinstance(parsed, dict):
        return Verdict(
            step="responds",
            ok=False,
            reason=f"top-level JSON was {type(parsed).__name__}, not object",
        )
    return Verdict(step="responds", ok=True)


# --------------------------------------------------------------------------- #
# classify_para
# --------------------------------------------------------------------------- #


def judge_classify_para(actual: dict[str, Any] | None, expected: ExpectedClassify) -> Verdict:
    if actual is None:
        return Verdict(step="classify_para", ok=False, reason="step did not produce output")
    got = actual.get("type")
    if got == expected.type:
        return Verdict(step="classify_para", ok=True, detail={"type": got})
    return Verdict(
        step="classify_para",
        ok=False,
        reason=f"expected {expected.type!r}, got {got!r}",
        detail={"expected": expected.type, "got": got},
    )


# --------------------------------------------------------------------------- #
# pick_quest
# --------------------------------------------------------------------------- #


def judge_pick_quest(actual: dict[str, Any] | None, expected: ExpectedPickQuest) -> Verdict:
    if actual is None:
        return Verdict(step="pick_quest", ok=False, reason="step did not produce output")

    skipped = bool(actual.get("skipped"))
    if expected.skipped:
        if skipped:
            return Verdict(step="pick_quest", ok=True, detail={"skipped": True})
        return Verdict(
            step="pick_quest",
            ok=False,
            reason="expected step to skip (resource), but it ran",
            detail={"got": actual.get("quests")},
        )

    if skipped:
        return Verdict(
            step="pick_quest",
            ok=False,
            reason="step skipped, but a Quest was expected",
        )

    picked = frozenset(actual.get("quests") or [])
    for acc in expected.acceptable:
        if picked == acc:
            return Verdict(
                step="pick_quest",
                ok=True,
                detail={"picked": sorted(picked), "matched": sorted(acc)},
            )
    return Verdict(
        step="pick_quest",
        ok=False,
        reason="picked set matched no acceptable set",
        detail={
            "picked": sorted(picked),
            "acceptable": [sorted(a) for a in expected.acceptable],
        },
    )


# --------------------------------------------------------------------------- #
# propose_filename
# --------------------------------------------------------------------------- #

# canonical form: lowercase, drop `.md`, strip non-alphanumerics to spaces,
# collapse whitespace. Catches Title Case vs casing differences and minor
# punctuation drift. Won't catch semantic word-choice differences — those
# are real failures and should fail the judge.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def canonical_filename(name: str) -> str:
    s = name.strip().lower()
    if s.endswith(".md"):
        s = s[:-3]
    s = _NON_ALNUM.sub(" ", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s


def judge_propose_filename(actual: dict[str, Any] | None, expected: ExpectedFilename) -> Verdict:
    if actual is None:
        return Verdict(step="propose_filename", ok=False, reason="step did not produce output")
    got = actual.get("filename")
    if not isinstance(got, str):
        return Verdict(
            step="propose_filename",
            ok=False,
            reason=f"filename was {type(got).__name__}, not string",
        )
    got_canon = canonical_filename(got)
    want_canon = canonical_filename(expected.canonical)
    if got_canon == want_canon:
        return Verdict(
            step="propose_filename",
            ok=True,
            detail={"filename": got, "canonical": got_canon},
        )
    return Verdict(
        step="propose_filename",
        ok=False,
        reason="canonical filename mismatch",
        detail={
            "got": got,
            "got_canonical": got_canon,
            "expected_canonical": want_canon,
        },
    )


# --------------------------------------------------------------------------- #
# plan_destination (pure step, mostly an integration sanity check)
# --------------------------------------------------------------------------- #


def judge_plan_destination(actual: dict[str, Any] | None, expected: ExpectedDestination) -> Verdict:
    if actual is None:
        return Verdict(step="plan_destination", ok=False, reason="step did not produce output")
    got = actual.get("destination")
    if got == expected.destination:
        return Verdict(step="plan_destination", ok=True, detail={"destination": got})
    return Verdict(
        step="plan_destination",
        ok=False,
        reason=f"expected {expected.destination!r}, got {got!r}",
        detail={"expected": expected.destination, "got": got},
    )


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

JUDGES: dict[str, Any] = {
    "classify_para": judge_classify_para,
    "pick_quest": judge_pick_quest,
    "propose_filename": judge_propose_filename,
    "plan_destination": judge_plan_destination,
}


def judge_step(
    step: str,
    actual: dict[str, Any] | None,
    expected: Expected,
) -> Verdict:
    """Dispatch to the right per-step judge based on ``step`` name."""
    fn = JUDGES.get(step)
    if fn is None:
        return Verdict(step=step, ok=False, reason=f"no judge for step {step!r}")
    spec = getattr(expected, step, None)
    if spec is None:
        return Verdict(step=step, ok=False, reason=f"fixture has no expected.{step}")
    result: Verdict = fn(actual, spec)
    return result


__all__ = [
    "JUDGES",
    "Verdict",
    "canonical_filename",
    "judge_classify_para",
    "judge_pick_quest",
    "judge_plan_destination",
    "judge_propose_filename",
    "judge_responds",
    "judge_step",
]

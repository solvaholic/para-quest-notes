"""Per-step judges for the eval harness.

Each judge takes the workflow's actual output (or the escalation that
came back instead) plus the fixture's expected payload, and returns a
``Verdict``.

Verdicts roll up into the report. Keep judges deterministic and cheap.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any

from para_quest_notes.eval.fixtures import (
    Expected,
    ExpectedClassify,
    ExpectedDestination,
    ExpectedFilename,
    ExpectedGenerateOutcome,
    ExpectedPickQuest,
    ExpectedTemplateMerge,
)


@dataclass
class Verdict:
    """Result of judging one (step, fixture) pair."""

    step: str
    ok: bool
    reason: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# `responds`: did the LLM produce anything parseable / non-empty at all?
# --------------------------------------------------------------------------- #


def judge_responds(raw_text: str | None) -> Verdict:
    """Cheap gate for JSON steps: parseable JSON object response, or not."""
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


def judge_text_responds(raw_text: str | None) -> Verdict:
    """Cheap gate for prose steps: any non-empty text counts as a response."""
    if raw_text is None:
        return Verdict(step="responds", ok=False, reason="no LLM call recorded")
    if not raw_text.strip():
        return Verdict(step="responds", ok=False, reason="empty response")
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
# punctuation drift. Won't catch semantic word-choice differences - those
# are real failures and should fail the judge.
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_WORD = re.compile(r"[a-z0-9]+")


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
    want_canons = [canonical_filename(c) for c in expected.acceptable]
    if got_canon in want_canons:
        return Verdict(
            step="propose_filename",
            ok=True,
            detail={"filename": got, "canonical": got_canon},
        )
    return Verdict(
        step="propose_filename",
        ok=False,
        reason="canonical filename matched no acceptable name",
        detail={
            "got": got,
            "got_canonical": got_canon,
            "acceptable_canonical": want_canons,
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
# generate_outcome
# --------------------------------------------------------------------------- #


def judge_generate_outcome(
    actual: dict[str, Any] | None, expected: ExpectedGenerateOutcome
) -> Verdict:
    if actual is None:
        return Verdict(step="generate_outcome", ok=False, reason="step did not produce output")
    text = actual.get("outcome_text")
    if actual.get("action") != "generated" or not isinstance(text, str) or not text.strip():
        return Verdict(
            step="generate_outcome",
            ok=False,
            reason="step did not produce generated outcome text",
            detail={"actual": actual},
        )

    detail: dict[str, Any] = {"text_preview": text[:200]}
    if expected.keywords:
        lowered = text.lower()
        matched = [keyword for keyword in expected.keywords if keyword.lower() in lowered]
        needed = max(1, math.ceil(len(expected.keywords) * 0.6))
        detail.update(
            {
                "matched_keywords": matched,
                "missing_keywords": [k for k in expected.keywords if k not in matched],
                "needed": needed,
            }
        )
        if len(matched) < needed:
            return Verdict(
                step="generate_outcome",
                ok=False,
                reason="keyword coverage below threshold",
                detail=detail,
            )

    if expected.text is not None:
        overlap = _jaccard(_tokens(text), _tokens(expected.text))
        detail["text_jaccard"] = overlap
        if overlap < 0.25:
            return Verdict(
                step="generate_outcome",
                ok=False,
                reason="reference-text overlap below threshold",
                detail=detail,
            )

    return Verdict(step="generate_outcome", ok=True, detail=detail)


def judge_template_merge(
    actual: dict[str, Any] | None,
    expected: ExpectedTemplateMerge,
) -> Verdict:
    if actual is None:
        return Verdict(step="merge_template", ok=False, reason="step did not produce output")
    placements = actual.get("placements")
    if actual.get("status") != "merged" or not isinstance(placements, list):
        return Verdict(
            step="merge_template",
            ok=False,
            reason="step did not produce a merged placement list",
            detail={"actual": actual},
        )
    got: list[tuple[str, str]] = []
    for placement in placements:
        if not isinstance(placement, dict):
            return Verdict(
                step="merge_template",
                ok=False,
                reason="placement was not an object",
                detail={"actual": actual},
            )
        block_id = placement.get("block_id")
        section_id = placement.get("section_id")
        if not isinstance(block_id, str) or not isinstance(section_id, str):
            return Verdict(
                step="merge_template",
                ok=False,
                reason="placement IDs were not strings",
                detail={"actual": actual},
            )
        got.append((block_id, section_id))

    if tuple(got) == expected.placements:
        return Verdict(step="merge_template", ok=True, detail={"placements": got})
    return Verdict(
        step="merge_template",
        ok=False,
        reason="placement mapping did not match expected routing",
        detail={"expected": expected.placements, "got": got},
    )


def _tokens(text: str) -> set[str]:
    return {match.group(0) for match in _WORD.finditer(text.lower())}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


# --------------------------------------------------------------------------- #
# Dispatch
# --------------------------------------------------------------------------- #

JUDGES: dict[str, Any] = {
    "classify_para": judge_classify_para,
    "pick_quest": judge_pick_quest,
    "propose_filename": judge_propose_filename,
    "plan_destination": judge_plan_destination,
    "generate_outcome": judge_generate_outcome,
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
    "judge_generate_outcome",
    "judge_pick_quest",
    "judge_plan_destination",
    "judge_propose_filename",
    "judge_responds",
    "judge_step",
    "judge_template_merge",
    "judge_text_responds",
]

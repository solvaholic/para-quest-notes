"""Step 2: classify_para (LLM, with heuristic pre-classification).

Picks one of ``project | area | resource``. Schema:
``{"type": str, "confidence": float, "reason": str}``.

A heuristic layer runs before the LLM call and short-circuits for
obviously-classifiable notes (e.g., body is all code blocks, a single
URL, or empty). This saves an LLM round-trip and avoids spurious
escalations on trivially-classifiable content.
"""

from __future__ import annotations

import re

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import Prompt
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.workflows.ingest_inbox.steps._llm import (
    call_llm_json,
    confidence_ok,
    require,
)
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanResult

VALID_TYPES = ("project", "area", "resource")
BODY_PREVIEW_CHARS = 2000

# Matches a fenced code block (``` or ~~~, with optional language tag).
_FENCE_RE = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[^\n]*\n.*?^(?P=fence)\s*$",
    re.MULTILINE | re.DOTALL,
)

# A single URL line (optionally preceded/followed by one short description line).
_URL_RE = re.compile(r"^https?://\S+$")


def _heuristic_classify(body: str) -> str | None:
    """Return a PARA type if rules match, or None to fall through to LLM.

    Each rule targets notes whose classification is unambiguous from
    structure alone. Conservative: returns None on any doubt.
    """
    # Strip the leading H1 title line (already extracted by scan_note)
    # so we inspect only the content beneath the heading.
    raw_lines = body.splitlines(keepends=True)
    content_lines: list[str] = []
    skipped_title = False
    for ln in raw_lines:
        if not skipped_title and ln.strip().startswith("# "):
            skipped_title = True
            continue
        content_lines.append(ln)
    content = "".join(content_lines)
    stripped = content.strip()

    # Empty body (title-only note) -> resource.
    if not stripped:
        return "resource"

    # Body is entirely fenced code blocks (possibly multiple, separated
    # by blank lines).
    defenced = _FENCE_RE.sub("", stripped).strip()
    if not defenced:
        return "resource"

    # Body is a single URL with at most one short description line.
    non_blank = [ln for ln in stripped.splitlines() if ln.strip()]
    if len(non_blank) == 1 and _URL_RE.match(non_blank[0].strip()):
        return "resource"
    if len(non_blank) == 2:
        url_lines = [ln for ln in non_blank if _URL_RE.match(ln.strip())]
        if len(url_lines) == 1:
            other = next(ln for ln in non_blank if ln not in url_lines)
            if len(other.strip()) < 120:
                return "resource"

    # Body is a blockquote with no other prose.
    if non_blank and all(ln.strip().startswith(">") for ln in non_blank):
        return "resource"

    return None


class ClassifyPara:
    name = "classify_para"

    def __init__(self, prompt: Prompt, *, model: str | None = None):
        self.prompt = prompt
        self.model = model

    def run(self, ctx: StepContext) -> StepResult:
        scan: ScanResult = ctx.scratchpad["scan"]
        preset_type = scan.parsed.frontmatter.get("type")
        if isinstance(preset_type, str):
            normalized = preset_type.strip().lower()
            if normalized in VALID_TYPES:
                ctx.scratchpad["para_type"] = normalized
                ctx.scratchpad["para_reason"] = "used pre-set type from frontmatter"
                return StepResult(
                    name=self.name,
                    output={
                        "type": normalized,
                        "confidence": 1.0,
                        "reason": "used pre-set type from frontmatter",
                        "skipped": True,
                    },
                    meta={"type": normalized, "source": "frontmatter"},
                )

        body_preview = scan.parsed.body.strip()[:BODY_PREVIEW_CHARS]

        # Heuristic pre-classification: skip LLM for obvious resources.
        heuristic_type = _heuristic_classify(scan.parsed.body)
        if heuristic_type is not None:
            ctx.scratchpad["para_type"] = heuristic_type
            ctx.scratchpad["para_reason"] = "heuristic pre-classification"
            return StepResult(
                name=self.name,
                output={
                    "type": heuristic_type,
                    "confidence": 1.0,
                    "reason": "heuristic pre-classification",
                    "skipped": True,
                },
                meta={"type": heuristic_type, "source": "heuristic"},
            )

        parsed = call_llm_json(
            ctx_llm=ctx.llm,
            prompt=self.prompt,
            render_vars={
                "title": scan.title,
                "body": body_preview or "(empty)",
            },
            step_name=self.name,
            model=self.model,
        )
        para_type = str(require(parsed, "type", step=self.name, expected="string"))
        confidence = require(parsed, "confidence", step=self.name, expected="number")
        reason = str(parsed.get("reason", ""))

        if para_type not in VALID_TYPES:
            raise EscalateToUser(
                step=self.name,
                reason=f"LLM returned unknown PARA type {para_type!r}",
                options=[{"type": t} for t in VALID_TYPES],
                context={"reason": reason},
            )
        if not confidence_ok(confidence):
            raise EscalateToUser(
                step=self.name,
                reason="low confidence in PARA classification",
                options=[{"type": t} for t in VALID_TYPES],
                context={"type": para_type, "confidence": confidence, "reason": reason},
            )

        ctx.scratchpad["para_type"] = para_type
        ctx.scratchpad["para_reason"] = reason
        return StepResult(
            name=self.name,
            output={"type": para_type, "confidence": confidence, "reason": reason},
            meta={"type": para_type, "confidence": confidence},
        )

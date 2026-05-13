"""LLM outcome generation for ``pqn-archive``."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import Prompt
from para_quest_notes.adapter.step import StepContext, StepResult

_COMPLETED_TASK = re.compile(r"^([ \t]*[-*+] )\[x\] (.*)$", re.IGNORECASE)
_FENCE = re.compile(r"^([ \t]*)(```|~~~)")
_WIKILINK = re.compile(r"\[\[([^\[\]|#]+?)(#[^\[\]|]+?)?(\|[^\[\]]+?)?\]\]")
_SNIPPET_MAX = 160


class GenerateOutcome:
    name = "generate_outcome"

    def __init__(self, prompt: Prompt, *, model: str | None = None):
        self.prompt = prompt
        self.model = model

    def run(self, ctx: StepContext) -> StepResult:
        if not ctx.scratchpad.get("needs_generate_outcome"):
            return StepResult(name=self.name, output={"skipped": True}, meta={"skipped": True})

        split = ctx.scratchpad["split"]
        body = split.body.strip() or "(empty)"
        completed_task_lines = list(
            ctx.scratchpad.get("completed_task_lines") or extract_completed_task_lines(split.body)
        )
        inbound_links = list(
            ctx.scratchpad.get("inbound_links")
            or discover_inbound_links(
                ctx.vault,
                target_stem=_note_title(ctx),
                source_abs=ctx.scratchpad.get("source_abs"),
            )
        )

        response_text = call_llm_text(
            ctx=ctx,
            prompt=self.prompt,
            render_vars={
                "body": body,
                "completed_tasks": _render_completed_tasks(completed_task_lines),
                "inbound_links": _render_inbound_links(inbound_links),
            },
            step_name=self.name,
            model=self.model,
        )
        if not response_text:
            raise EscalateToUser(
                step=self.name,
                reason="LLM returned empty response while generating Outcome",
                options=[],
                context={"source": ctx.scratchpad["source_rel"], "prompt_id": self.prompt.id},
            )
        if response_text == "INSUFFICIENT_CONTEXT":
            raise EscalateToUser(
                step=self.name,
                reason=(
                    "note body is too sparse to generate a meaningful Outcome; "
                    "write one by hand and re-run with --outcome"
                ),
                options=[],
                context={"source": ctx.scratchpad["source_rel"]},
            )

        ctx.scratchpad["completed_task_lines"] = completed_task_lines
        ctx.scratchpad["inbound_links"] = inbound_links
        ctx.scratchpad["outcome_action"] = "generated"
        ctx.scratchpad["outcome_text"] = response_text
        return StepResult(
            name=self.name,
            output={
                "action": "generated",
                "outcome_text": response_text,
                "completed_tasks": len(completed_task_lines),
                "inbound_links": len(inbound_links),
            },
            meta={
                "completed_tasks": len(completed_task_lines),
                "inbound_links": len(inbound_links),
            },
        )


def call_llm_text(
    *,
    ctx: StepContext,
    prompt: Prompt,
    render_vars: dict[str, Any],
    step_name: str,
    model: str | None = None,
    temperature: float = 0.0,
) -> str:
    if ctx.llm is None:
        raise EscalateToUser(
            step=step_name,
            reason="no LLM client configured",
            options=[],
            context={},
        )
    rendered = prompt.render(**render_vars)
    response = ctx.llm.generate_text(
        rendered,
        model=model,
        temperature=temperature,
        prompt_id=prompt.id,
    )
    text = (response.text or "").strip()
    prompt_hash = prompt.id.split("@", 1)[1] if "@" in prompt.id else ""
    ctx.emit(
        {
            "event": "llm.complete",
            "step": step_name,
            "model": response.model,
            "prompt_id": prompt.id,
            "prompt_hash": prompt_hash,
            "raw_output": text,
            "latency_ms": response.latency_ms,
        }
    )
    return text


def extract_completed_task_lines(body: str) -> list[str]:
    found: list[str] = []
    in_fence = False
    fence_marker: str | None = None
    for line in body.splitlines():
        m_fence = _FENCE.match(line)
        if m_fence is not None:
            marker = m_fence.group(2)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            continue
        if in_fence:
            continue
        if _COMPLETED_TASK.match(line):
            found.append(line.strip())
    return found


def discover_inbound_links(
    vault: Path | None,
    *,
    target_stem: str,
    source_abs: Path | None = None,
) -> list[dict[str, str]]:
    if vault is None or not target_stem:
        return []

    target = target_stem.strip().lower()
    hits: list[dict[str, str]] = []
    for md in sorted(vault.rglob("*.md")):
        if source_abs is not None and md.resolve() == source_abs.resolve():
            continue
        try:
            rel = md.relative_to(vault)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == "archive":
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        snippet = _first_matching_line(text, target)
        if snippet is None:
            continue
        hit = {"basename": md.stem}
        if snippet:
            hit["snippet"] = snippet
        hits.append(hit)
    return hits


def _first_matching_line(text: str, target: str) -> str | None:
    for line in text.splitlines():
        for match in _WIKILINK.finditer(line):
            if match.group(1).strip().lower() == target:
                snippet = line.strip()
                if len(snippet) > _SNIPPET_MAX:
                    return snippet[: _SNIPPET_MAX - 3].rstrip() + "..."
                return snippet
    return None


def _note_title(ctx: StepContext) -> str:
    title = ctx.scratchpad.get("note_title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    source_rel = str(ctx.scratchpad.get("source_rel") or "")
    return Path(source_rel).stem


def _render_completed_tasks(lines: list[str]) -> str:
    if not lines:
        return "- (none found)"
    return "\n".join(lines)


def _render_inbound_links(links: list[dict[str, str]]) -> str:
    if not links:
        return "- (none found)"
    rendered: list[str] = []
    for link in links:
        basename = link.get("basename", "")
        snippet = link.get("snippet", "")
        if basename and snippet:
            rendered.append(f"- {basename}: {snippet}")
        elif basename:
            rendered.append(f"- {basename}")
    return "\n".join(rendered) if rendered else "- (none found)"


__all__ = [
    "GenerateOutcome",
    "call_llm_text",
    "discover_inbound_links",
    "extract_completed_task_lines",
]

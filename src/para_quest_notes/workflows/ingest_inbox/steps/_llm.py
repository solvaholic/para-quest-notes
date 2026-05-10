"""Shared LLM-step helpers.

LLM steps in this workflow follow the same shape: render a prompt,
call the LLM with ``format=json``, parse the response, validate it
against a tiny hand-rolled schema, escalate on failure or low
confidence.

We avoid pulling in ``jsonschema`` for now — schemas here are small
enough that explicit per-step validation keeps the dep list short and
errors targeted.
"""

from __future__ import annotations

import json
from typing import Any

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import Prompt

CONFIDENCE_FLOOR = 0.5


def call_llm_json(
    *,
    ctx_llm: Any,
    prompt: Prompt,
    render_vars: dict[str, Any],
    step_name: str,
    model: str | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Render + call + parse JSON. Escalates on parse failure."""
    if ctx_llm is None:
        raise EscalateToUser(
            step=step_name,
            reason="no LLM client configured",
            options=[],
            context={},
        )
    rendered = prompt.render(**render_vars)
    response = ctx_llm.generate(
        rendered,
        model=model,
        format="json",
        temperature=temperature,
        prompt_id=prompt.id,
    )
    text = (response.text or "").strip()
    if not text:
        raise EscalateToUser(
            step=step_name,
            reason="LLM returned empty response",
            options=[],
            context={"prompt_id": prompt.id, "model": response.model},
        )
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EscalateToUser(
            step=step_name,
            reason=f"LLM output was not valid JSON: {exc}",
            options=[],
            context={"prompt_id": prompt.id, "raw": text[:500]},
        ) from None
    if not isinstance(parsed, dict):
        raise EscalateToUser(
            step=step_name,
            reason="LLM output JSON was not an object",
            options=[],
            context={"prompt_id": prompt.id, "raw": text[:500]},
        )
    return parsed


def require(parsed: dict[str, Any], key: str, *, step: str, expected: str) -> Any:
    if key not in parsed:
        raise EscalateToUser(
            step=step,
            reason=f"LLM output missing required key '{key}' ({expected})",
            options=[],
            context={"raw": parsed},
        )
    return parsed[key]


def confidence_ok(value: Any) -> bool:
    try:
        return float(value) >= CONFIDENCE_FLOOR
    except (TypeError, ValueError):
        return False

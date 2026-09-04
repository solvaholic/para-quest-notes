"""Lossless LLM routing of stdin blocks into a selected template."""

from __future__ import annotations

import json
from typing import Any

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.prompts import Prompt
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import merge, split_note
from para_quest_notes.workflows.create.contract import CreateInputs
from para_quest_notes.workflows.create.routing import (
    InputBlock,
    TemplateSection,
    catalog_template_sections,
    merge_routed_blocks,
    split_input_blocks,
)
from para_quest_notes.workflows.create.templates import (
    TemplateNotFoundError,
    build_template_variables,
    get_template_config,
    load_template,
    render_template,
    select_template_name,
)


class MergeTemplate:
    name = "merge_template"

    def __init__(
        self,
        prompt: Prompt,
        *,
        today: str,
        apply: bool,
        model: str | None = None,
    ):
        self.prompt = prompt
        self.today = today
        self.apply = apply
        self.model = model

    def run(self, ctx: StepContext) -> StepResult:
        inputs: CreateInputs = ctx.scratchpad["inputs"]
        if not inputs.merge_template:
            return StepResult(name=self.name, output={"skipped": True}, meta={"skipped": True})

        if inputs.body is None or not inputs.body.strip():
            raise EscalateToUser(
                step=self.name,
                reason="--merge-template requires non-empty stdin",
                options=[],
                context={},
            )
        if ctx.vault is None:
            raise EscalateToUser(
                step=self.name,
                reason="--merge-template requires a resolved vault",
                options=[],
                context={},
            )

        config_workflows = ctx.config.workflows if ctx.config else {}
        template_name = select_template_name(inputs, config_workflows=config_workflows)
        if template_name is None:
            raise EscalateToUser(
                step=self.name,
                reason=(
                    "--merge-template requires a selected template "
                    "(use --template or configure a per-type default)"
                ),
                options=[],
                context={},
            )

        template_dir, _ = get_template_config(config_workflows)
        try:
            raw_template = load_template(
                template_name,
                vault=ctx.vault,
                template_dir=template_dir,
            )
        except TemplateNotFoundError as exc:
            raise EscalateToUser(
                step=self.name,
                reason=str(exc),
                options=[],
                context={"template": template_name},
            ) from None

        title: str = ctx.scratchpad["title"]
        variables = build_template_variables(inputs, title=title, today=self.today)
        split = split_note(raw_template)
        template_frontmatter = merge(split.backmatter, split.frontmatter)
        template_body = render_template(split.body, variables)
        rendered_stdin = render_template(inputs.body, variables)
        blocks = split_input_blocks(rendered_stdin)
        if not blocks:
            raise EscalateToUser(
                step=self.name,
                reason="--merge-template requires non-empty stdin",
                options=[],
                context={},
            )
        sections = catalog_template_sections(template_body)
        if not self.apply:
            ctx.scratchpad["deferred_template_body"] = template_body
            ctx.scratchpad["deferred_template_frontmatter"] = template_frontmatter
            ctx.scratchpad["deferred_template_name"] = template_name
            return StepResult(
                name=self.name,
                output={
                    "status": "deferred",
                    "template": template_name,
                    "input_blocks": len(blocks),
                },
                meta={
                    "status": "deferred",
                    "template": template_name,
                    "input_blocks": len(blocks),
                    "template_sections": len(sections),
                },
            )

        parsed = self._call_llm(ctx, blocks=blocks, sections=sections)
        assignments = _validate_routing_plan(parsed, blocks=blocks, sections=sections)
        merged_body = merge_routed_blocks(
            template_body,
            sections=sections,
            blocks=blocks,
            assignments=assignments,
        )

        unsorted_blocks = sum(target == "unsorted" for target in assignments.values())
        routed_blocks = len(blocks) - unsorted_blocks
        ctx.scratchpad["merged_template_body"] = merged_body
        ctx.scratchpad["merged_template_frontmatter"] = template_frontmatter
        ctx.scratchpad["merged_template_name"] = template_name
        return StepResult(
            name=self.name,
            output={
                "status": "merged",
                "template": template_name,
                "input_blocks": len(blocks),
                "routed_blocks": routed_blocks,
                "unsorted_blocks": unsorted_blocks,
                "placements": [
                    {"block_id": block.id, "section_id": assignments[block.id]} for block in blocks
                ],
            },
            meta={
                "template": template_name,
                "input_blocks": len(blocks),
                "routed_blocks": routed_blocks,
                "unsorted_blocks": unsorted_blocks,
            },
        )

    def _call_llm(
        self,
        ctx: StepContext,
        *,
        blocks: list[InputBlock],
        sections: list[TemplateSection],
    ) -> dict[str, Any]:
        if ctx.llm is None:
            raise EscalateToUser(
                step=self.name,
                reason="no LLM client configured",
                options=[],
                context={},
            )

        rendered = self.prompt.render(
            sections_json=json.dumps(
                [
                    {
                        "id": section.id,
                        "heading": section.heading,
                        "level": section.level,
                        "path": list(section.path),
                    }
                    for section in sections
                ],
                ensure_ascii=False,
                indent=2,
            ),
            blocks_json=json.dumps(
                [{"id": block.id, "text": block.text} for block in blocks],
                ensure_ascii=False,
                indent=2,
            ),
        )
        response = ctx.llm.generate(
            rendered,
            model=self.model,
            format="json",
            temperature=0.0,
            prompt_id=self.prompt.id,
        )
        text = (response.text or "").strip()
        prompt_hash = self.prompt.id.split("@", 1)[1] if "@" in self.prompt.id else ""
        if not text:
            ctx.emit(
                {
                    "event": "llm.complete",
                    "step": self.name,
                    "model": response.model,
                    "prompt_id": self.prompt.id,
                    "prompt_hash": prompt_hash,
                    "raw_output": text,
                    "parsed_output": None,
                    "latency_ms": response.latency_ms,
                }
            )
            raise EscalateToUser(
                step=self.name,
                reason="LLM returned empty response",
                options=[],
                context={"prompt_id": self.prompt.id, "model": response.model},
            )

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            ctx.emit(
                {
                    "event": "llm.complete",
                    "step": self.name,
                    "model": response.model,
                    "prompt_id": self.prompt.id,
                    "prompt_hash": prompt_hash,
                    "raw_output": text,
                    "parsed_output": None,
                    "latency_ms": response.latency_ms,
                }
            )
            raise EscalateToUser(
                step=self.name,
                reason=f"LLM output was not valid JSON: {exc}",
                options=[],
                context={"prompt_id": self.prompt.id, "raw": text[:500]},
            ) from None

        ctx.emit(
            {
                "event": "llm.complete",
                "step": self.name,
                "model": response.model,
                "prompt_id": self.prompt.id,
                "prompt_hash": prompt_hash,
                "raw_output": text,
                "parsed_output": parsed,
                "latency_ms": response.latency_ms,
            }
        )
        if not isinstance(parsed, dict):
            raise EscalateToUser(
                step=self.name,
                reason="LLM output JSON was not an object",
                options=[],
                context={"prompt_id": self.prompt.id, "raw": text[:500]},
            )
        return parsed


def _validate_routing_plan(
    parsed: dict[str, Any],
    *,
    blocks: list[InputBlock],
    sections: list[TemplateSection],
) -> dict[str, str]:
    unexpected_top = set(parsed) - {"placements"}
    if unexpected_top:
        _invalid(f"LLM output had unexpected key(s): {sorted(unexpected_top)}")
    if "placements" not in parsed:
        _invalid("LLM output missing required key 'placements' (list)")
    placements = parsed["placements"]
    if not isinstance(placements, list):
        _invalid("LLM output key 'placements' must be a list")

    valid_blocks = {block.id for block in blocks}
    valid_sections = {section.id for section in sections}
    assignments: dict[str, str] = {}
    for index, placement in enumerate(placements):
        if not isinstance(placement, dict):
            _invalid(f"placement {index} must be an object")
        unexpected = set(placement) - {"block_id", "section_id"}
        if unexpected:
            _invalid(f"placement {index} had unexpected key(s): {sorted(unexpected)}")
        missing = {"block_id", "section_id"} - set(placement)
        if missing:
            _invalid(f"placement {index} missing required key(s): {sorted(missing)}")

        block_id = placement["block_id"]
        section_id = placement["section_id"]
        if not isinstance(block_id, str) or not isinstance(section_id, str):
            _invalid(f"placement {index} block_id and section_id must be strings")
        if block_id not in valid_blocks:
            _invalid(f"placement {index} used unknown block_id {block_id!r}")
        if block_id in assignments:
            _invalid(f"LLM routing plan had duplicate block_id {block_id!r}")
        if section_id != "unsorted" and section_id not in valid_sections:
            _invalid(f"placement {index} used unknown section_id {section_id!r}")
        assignments[block_id] = section_id

    missing_blocks = sorted(valid_blocks - set(assignments))
    if missing_blocks:
        _invalid(
            f"LLM routing plan did not account for every stdin block (missing: {missing_blocks})"
        )
    return assignments


def _invalid(reason: str) -> None:
    raise EscalateToUser(
        step="merge_template",
        reason=reason,
        options=[],
        context={},
    )


__all__ = ["MergeTemplate"]

"""Render frontmatter + body for a single note.

Inputs: a seed item (Project / Area / Resource / inbox idea / daily
note marker) and a :class:`Shape`. Output: a string ready to write to
disk.

Prose comes from Faker (seeded). Structure (headings, tasks,
wikilinks) comes from the seeds vocabulary so the ingest workflow has
something realistic to reason over.
"""

from __future__ import annotations

import datetime as dt
import random
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import yaml
from faker import Faker

from para_quest_notes.corpus.seeds import (
    AreaSeed,
    MainQuest,
    ProjectSeed,
    ResourceSeed,
    Seeds,
    SideQuest,
)
from para_quest_notes.corpus.shapes import FrontmatterKind, Quirk, Shape


@dataclass
class RenderInputs:
    """Everything the renderer needs to emit one note."""

    title: str
    type_: str  # "project" | "area" | "resource"
    quest: str  # "main" | "side" | "none"
    supports: tuple[str, ...]  # wikilink targets without brackets
    shape: Shape
    extra_wikilinks: tuple[str, ...] = ()  # other notes to link to from the body


# --------------------------------------------------------------------------- #
# Frontmatter rendering
# --------------------------------------------------------------------------- #


def _wikilink(target: str) -> str:
    return f"[[{target}]]"


def _yaml_block(data: dict[str, Any]) -> str:
    """Render a YAML frontmatter block. Wikilinks are quoted because
    `[` is a YAML flow-sequence marker; the spec calls this out."""
    body = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    return f"---\n{body}---\n"


def render_frontmatter(inputs: RenderInputs, faker: Faker, seeds: Seeds) -> str:
    kind = inputs.shape.frontmatter_kind
    if kind is FrontmatterKind.NONE:
        return ""

    if kind is FrontmatterKind.OBSIDIAN_ONLY:
        # Two random tags, no PARA fields. Sorted for determinism within
        # a single render call (Faker is seeded; sort just guards against
        # set-iteration order across Python versions).
        tags = sorted(faker.random_elements(elements=seeds.obsidian_tags, length=2, unique=True))
        return _yaml_block({"tags": list(tags)})

    if kind is FrontmatterKind.PARTIAL_PARA:
        # Has type, but missing Quest signal — exactly the case that
        # forces the ingest workflow to escalate or infer.
        return _yaml_block({"type": inputs.type_})

    # FULL — but honor the MISSING_SUPPORTS quirk if set.
    data: dict[str, Any] = {"type": inputs.type_, "quest-kind": inputs.quest}
    if not inputs.shape.has(Quirk.MISSING_SUPPORTS):
        data["supports"] = [_wikilink(s) for s in inputs.supports]
    return _yaml_block(data)


# --------------------------------------------------------------------------- #
# Body rendering
# --------------------------------------------------------------------------- #


def _paragraph(faker: Faker, sentences: int = 3) -> str:
    return faker.paragraph(nb_sentences=sentences)


def _task_lines(
    faker: Faker,
    seeds: Seeds,
    *,
    count: int,
    closed: bool,
    extra_links: Iterable[str] = (),
) -> list[str]:
    extras = list(extra_links)
    out: list[str] = []
    for _ in range(count):
        verb = faker.random_element(seeds.task_verbs)
        noun = faker.word().title()
        marker = "x" if closed else " "
        line = f"- [{marker}] {verb} {noun}"
        if extras and faker.random.random() < 0.4:
            line += f" — see {_wikilink(faker.random_element(extras))}"
        out.append(line)
    return out


def _quest_mention(name: str) -> str:
    return f"This relates to {_wikilink(name)}."


def render_body(inputs: RenderInputs, faker: Faker, seeds: Seeds) -> str:
    shape = inputs.shape
    parts: list[str] = [f"# {inputs.title}", "", _paragraph(faker, sentences=4), ""]

    # Resource notes get a short reference-style body — no tasks, may
    # include a "See also" section.
    if inputs.type_ == "resource":
        parts.extend(["## Notes", "", _paragraph(faker, sentences=3), ""])
        if inputs.extra_wikilinks:
            parts.append("## See also")
            parts.append("")
            for link in inputs.extra_wikilinks:
                parts.append(f"- {_wikilink(link)}")
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"

    # Projects and Areas: optional tasks section.
    if shape.has(Quirk.HAS_TASKS):
        closed = shape.has(Quirk.CLOSED_TASKS_ONLY)
        parts.extend(["## Tasks", ""])
        parts.extend(
            _task_lines(
                faker,
                seeds,
                count=faker.random_int(min=2, max=5),
                closed=closed,
                extra_links=inputs.extra_wikilinks,
            )
        )
        parts.append("")

    # Ambiguous-quest quirk: drop in mentions of a couple of unrelated
    # Quests so the ingest workflow has to disambiguate.
    if shape.has(Quirk.AMBIGUOUS_QUEST):
        # Sort to keep ordering deterministic across interpreter starts:
        # set difference iteration order is randomized by PYTHONHASHSEED.
        distractor_pool = sorted(seeds.quest_names - set(inputs.supports))
        if distractor_pool:
            faker.random.shuffle(distractor_pool)
            for d in distractor_pool[:2]:
                parts.append(_quest_mention(d))
            parts.append("")

    if shape.has(Quirk.BROKEN_WIKILINK):
        parts.append(
            f"Earlier idea: {_wikilink('Nonexistent ' + faker.word().title())} (no longer used)."
        )
        parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def render_note(inputs: RenderInputs, faker: Faker, seeds: Seeds) -> str:
    return render_frontmatter(inputs, faker, seeds) + render_body(inputs, faker, seeds)


# --------------------------------------------------------------------------- #
# Convenience constructors for each top-level seed kind
# --------------------------------------------------------------------------- #


def inputs_for_main_quest(quest: MainQuest, shape: Shape) -> RenderInputs:
    return RenderInputs(
        title=quest.name,
        type_="area",
        quest="main",
        supports=(quest.name,),  # Main Quests list themselves
        shape=shape,
    )


def inputs_for_side_quest(quest: SideQuest, shape: Shape) -> RenderInputs:
    return RenderInputs(
        title=quest.name,
        type_="area",
        quest="side",
        supports=quest.supports,
        shape=shape,
    )


def inputs_for_area(area: AreaSeed, shape: Shape) -> RenderInputs:
    return RenderInputs(
        title=area.name,
        type_="area",
        quest="none",
        supports=area.supports,
        shape=shape,
    )


def inputs_for_project(
    project: ProjectSeed, shape: Shape, extra_links: tuple[str, ...] = ()
) -> RenderInputs:
    return RenderInputs(
        title=project.title,
        type_="project",
        quest="none",
        supports=project.supports,
        shape=shape,
        extra_wikilinks=extra_links,
    )


def inputs_for_resource(
    resource: ResourceSeed, shape: Shape, extra_links: tuple[str, ...] = ()
) -> RenderInputs:
    return RenderInputs(
        title=resource.title,
        type_="resource",
        quest="none",
        supports=(),
        shape=shape,
        extra_wikilinks=extra_links or resource.parents,
    )


# --------------------------------------------------------------------------- #
# Inbox + daily renderers — these don't map to a seed item, just shapes.
# --------------------------------------------------------------------------- #


def render_inbox_note(faker: Faker, seeds: Seeds, shape: Shape) -> tuple[str, str]:
    """Return ``(filename_stem, content)`` for an inbox note."""
    title = faker.sentence(nb_words=4).rstrip(".")
    inputs = RenderInputs(
        title=title,
        type_="resource",  # inbox notes haven't been classified yet
        quest="none",
        supports=(),
        shape=shape,
    )
    return title, render_note(inputs, faker, seeds)


def render_daily_note(faker: Faker, seeds: Seeds, date: dt.date, shape: Shape) -> str:
    """Render a daily note for ``date``. Always bare-ish per spec."""
    parts = [
        f"# {date.isoformat()}",
        "",
        _paragraph(faker, sentences=2),
        "",
        "## Tasks",
        "",
    ]
    parts.extend(_task_lines(faker, seeds, count=faker.random_int(min=1, max=4), closed=False))
    parts.append("")
    body = "\n".join(parts).rstrip() + "\n"
    fm = render_frontmatter(
        RenderInputs(
            title=date.isoformat(),
            type_="resource",
            quest="none",
            supports=(),
            shape=shape,
        ),
        faker,
        seeds,
    )
    return fm + body


__all__ = [
    "RenderInputs",
    "inputs_for_area",
    "inputs_for_main_quest",
    "inputs_for_project",
    "inputs_for_resource",
    "inputs_for_side_quest",
    "render_body",
    "render_daily_note",
    "render_frontmatter",
    "render_inbox_note",
    "render_note",
]


# Faker.random_element / random_elements use Faker's own seeded RNG, so
# passing the stdlib `random.Random` we plumb everywhere isn't strictly
# necessary inside this module — the Faker instance is itself
# constructed with the seed. Keep that contract clear:
_ = random  # documentation: stdlib RNG owned by callers, not us.

"""Loader and validator for ``seeds.yaml``.

The seeds file holds the **vocabulary** the corpus generator draws
from: Main and Side Quests, Areas, Projects, Resources, plus task
verbs and other surface forms. It contains *no* personal data and is
intentionally generic so the public repo can ship with a believable
sample vault.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class MainQuest:
    name: str
    purpose: str


@dataclass(frozen=True)
class SideQuest:
    name: str
    supports: tuple[str, ...]


@dataclass(frozen=True)
class AreaSeed:
    name: str
    supports: tuple[str, ...]


@dataclass(frozen=True)
class ProjectSeed:
    title: str
    supports: tuple[str, ...]


@dataclass(frozen=True)
class ResourceSeed:
    title: str
    parents: tuple[str, ...]


@dataclass(frozen=True)
class Seeds:
    main_quests: tuple[MainQuest, ...]
    side_quests: tuple[SideQuest, ...]
    areas: tuple[AreaSeed, ...]
    projects: tuple[ProjectSeed, ...]
    resources: tuple[ResourceSeed, ...]
    task_verbs: tuple[str, ...]
    topic_dirs: tuple[str, ...]
    obsidian_tags: tuple[str, ...]

    @property
    def main_quest_names(self) -> set[str]:
        return {q.name for q in self.main_quests}

    @property
    def side_quest_names(self) -> set[str]:
        return {q.name for q in self.side_quests}

    @property
    def quest_names(self) -> set[str]:
        return self.main_quest_names | self.side_quest_names

    @property
    def area_names(self) -> set[str]:
        return {a.name for a in self.areas}


class SeedsError(ValueError):
    """Raised when ``seeds.yaml`` is malformed or has dangling references."""


def _str_tuple(value: Any, *, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SeedsError(f"{where}: expected list, got {type(value).__name__}")
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str):
            raise SeedsError(f"{where}[{i}]: expected string, got {type(item).__name__}")
        out.append(item)
    return tuple(out)


def _required_list(raw: dict[str, Any], key: str) -> list[Any]:
    if key not in raw or raw[key] is None:
        raise SeedsError(f"missing required key: {key!r}")
    value = raw[key]
    if not isinstance(value, list):
        raise SeedsError(f"{key!r}: expected list, got {type(value).__name__}")
    return list(value)


def _parse(raw: dict[str, Any]) -> Seeds:
    main_quests = tuple(
        MainQuest(name=str(item["name"]), purpose=str(item.get("purpose", "")))
        for item in _required_list(raw, "main_quests")
    )
    side_quests = tuple(
        SideQuest(
            name=str(item["name"]),
            supports=_str_tuple(item.get("supports"), where=f"side_quests[{i}].supports"),
        )
        for i, item in enumerate(_required_list(raw, "side_quests"))
    )
    areas = tuple(
        AreaSeed(
            name=str(item["name"]),
            supports=_str_tuple(item.get("supports"), where=f"areas[{i}].supports"),
        )
        for i, item in enumerate(_required_list(raw, "areas"))
    )
    projects = tuple(
        ProjectSeed(
            title=str(item["title"]),
            supports=_str_tuple(item.get("supports"), where=f"projects[{i}].supports"),
        )
        for i, item in enumerate(_required_list(raw, "projects"))
    )
    resources = tuple(
        ResourceSeed(
            title=str(item["title"]),
            parents=_str_tuple(item.get("parents"), where=f"resources[{i}].parents"),
        )
        for i, item in enumerate(_required_list(raw, "resources"))
    )

    seeds = Seeds(
        main_quests=main_quests,
        side_quests=side_quests,
        areas=areas,
        projects=projects,
        resources=resources,
        task_verbs=_str_tuple(_required_list(raw, "task_verbs"), where="task_verbs"),
        topic_dirs=_str_tuple(_required_list(raw, "topic_dirs"), where="topic_dirs"),
        obsidian_tags=_str_tuple(_required_list(raw, "obsidian_tags"), where="obsidian_tags"),
    )
    _validate_refs(seeds)
    return seeds


def _validate_refs(seeds: Seeds) -> None:
    """Every Quest reference must resolve, and Side Quests must support
    at least one Main Quest. Catches typos in seeds.yaml before they
    silently produce broken sample notes."""
    main = seeds.main_quest_names
    quests = seeds.quest_names
    areas = seeds.area_names

    for sq in seeds.side_quests:
        if not sq.supports:
            raise SeedsError(f"side_quest {sq.name!r}: must support at least one Main Quest")
        for ref in sq.supports:
            if ref not in main:
                raise SeedsError(
                    f"side_quest {sq.name!r} supports {ref!r}, which is not a Main Quest"
                )

    for area in seeds.areas:
        for ref in area.supports:
            if ref not in quests:
                raise SeedsError(f"area {area.name!r} supports {ref!r}, which is not a known Quest")

    for project in seeds.projects:
        if not project.supports:
            raise SeedsError(f"project {project.title!r}: must support at least one Quest")
        for ref in project.supports:
            if ref not in quests:
                raise SeedsError(
                    f"project {project.title!r} supports {ref!r}, which is not a known Quest"
                )

    for resource in seeds.resources:
        for ref in resource.parents:
            if ref not in areas:
                raise SeedsError(f"resource {resource.title!r} parent {ref!r} is not a known Area")


def load_seeds(path: Path | None = None) -> Seeds:
    """Load seeds from ``path`` (or the bundled ``seeds.yaml``)."""
    if path is None:
        text = (
            resources.files("para_quest_notes.corpus")
            .joinpath("seeds.yaml")
            .read_text(encoding="utf-8")
        )
    else:
        text = Path(path).read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    if not isinstance(raw, dict):
        raise SeedsError("top level of seeds.yaml must be a mapping")
    return _parse(raw)


# Re-export so ``from .seeds import *`` is meaningful, though we don't
# actually encourage star imports.
__all__ = [
    "AreaSeed",
    "MainQuest",
    "ProjectSeed",
    "ResourceSeed",
    "Seeds",
    "SeedsError",
    "SideQuest",
    "load_seeds",
]


# Suppress unused-import warning from ruff in case a downstream
# refactor drops the field default factory in dataclasses.
_ = field

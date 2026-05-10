"""Vault generator: pull it all together.

Walks the seeds, builds a directory tree under ``out``, writes notes,
and emits ``_corpus_manifest.json`` so eval fixtures can index the
output by shape.
"""

from __future__ import annotations

import datetime as dt
import json
import random
import shutil
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from faker import Faker

from para_quest_notes.corpus.render import (
    RenderInputs,
    inputs_for_area,
    inputs_for_main_quest,
    inputs_for_project,
    inputs_for_resource,
    inputs_for_side_quest,
    render_daily_note,
    render_inbox_note,
    render_note,
)
from para_quest_notes.corpus.seeds import (
    AreaSeed,
    ProjectSeed,
    ResourceSeed,
    Seeds,
    load_seeds,
)
from para_quest_notes.corpus.shapes import (
    FrontmatterKind,
    LocationKind,
    Quirk,
    Shape,
    sample_shape,
)

MANIFEST_FILENAME = "_corpus_manifest.json"
GENERATOR_VERSION = 1


# --------------------------------------------------------------------------- #
# Public dataclasses
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class GenerateOptions:
    """User-facing knobs for :func:`generate_vault`."""

    seed: int = 0
    projects: int = 6
    areas: int = 0  # 0 means "use every Area in seeds.yaml verbatim"
    resources: int = 0  # 0 means "use every Resource in seeds.yaml verbatim"
    inbox: int = 5
    daily: int = 7
    quirk_rate: float = 0.3
    write_manifest: bool = True
    clean: bool = False


# Default count map mirrors GenerateOptions defaults; surfaces them for
# CLI help text and for tests that assert on totals.
DEFAULT_COUNTS: dict[str, int] = {
    "projects": 6,
    "areas": 0,
    "resources": 0,
    "inbox": 5,
    "daily": 7,
}


@dataclass
class GeneratedFile:
    path: str  # vault-relative POSIX path
    location_kind: LocationKind
    frontmatter_kind: FrontmatterKind
    quirks: tuple[Quirk, ...]
    title: str
    type_: str  # PARA type label

    def to_manifest_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "title": self.title,
            "type": self.type_,
            "location_kind": self.location_kind.value,
            "frontmatter_kind": self.frontmatter_kind.value,
            "quirks": sorted(q.value for q in self.quirks),
        }


@dataclass
class GenerateResult:
    out: Path
    options: GenerateOptions
    files: list[GeneratedFile] = field(default_factory=list)

    @property
    def manifest_path(self) -> Path:
        return self.out / MANIFEST_FILENAME

    def to_manifest_dict(self) -> dict[str, object]:
        # `clean` is a runtime safety flag (wipe-or-error), not a corpus
        # property. Excluding it keeps the manifest stable regardless of
        # whether the user invoked with --clean.
        opts = {k: v for k, v in asdict(self.options).items() if k != "clean"}
        return {
            "generator_version": GENERATOR_VERSION,
            "options": opts,
            "files": sorted(
                (f.to_manifest_dict() for f in self.files),
                key=lambda d: d["path"],  # type: ignore[arg-type, return-value]
            ),
        }


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #


def _para_dir(type_: str) -> str:
    return {"project": "projects", "area": "areas", "resource": "resources"}[type_]


def _filename(title: str) -> str:
    """Title-case, .md, basic sanitization. Matches docs/notes-system.md."""
    cleaned = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    return f"{cleaned}.md"


def _path_for_inputs(
    inputs: RenderInputs, *, faker: Faker, seeds: Seeds, location_kind: LocationKind
) -> Path:
    fname = _filename(inputs.title)
    if location_kind is LocationKind.PARA:
        return Path(_para_dir(inputs.type_)) / fname
    if location_kind is LocationKind.TOPIC:
        topic = faker.random_element(seeds.topic_dirs)
        return Path(topic) / fname
    if location_kind is LocationKind.QUEST:
        quest_dir = (
            inputs.supports[0]
            if inputs.supports
            else faker.random_element(tuple(seeds.quest_names))
        )
        return Path(quest_dir) / fname
    if location_kind is LocationKind.INBOX:
        return Path("inbox") / fname
    raise ValueError(f"location_kind {location_kind!r} is not valid for arbitrary inputs")


def _daily_path(date: dt.date) -> Path:
    return (
        Path("resources/daily_notes")
        / f"{date.year:04d}"
        / f"{date.month:02d}"
        / f"{date.isoformat()}.md"
    )


# --------------------------------------------------------------------------- #
# Core generator
# --------------------------------------------------------------------------- #


def _ensure_out_dir(out: Path, clean: bool) -> None:
    if out.exists():
        if any(out.iterdir()):
            if not clean:
                raise FileExistsError(
                    f"output directory is not empty: {out} (pass clean=True / --clean to wipe)"
                )
            shutil.rmtree(out)
            out.mkdir(parents=True)
        # else: empty existing dir is fine
    else:
        out.mkdir(parents=True)
    # PARA top-levels — keep them present even if a category has 0 notes,
    # so the result always passes adapter.vault.is_vault().
    for sub in ("projects", "areas", "resources", "inbox", "archive"):
        (out / sub).mkdir(exist_ok=True)


def _location_for_seed_kind(rng: random.Random, type_: str) -> LocationKind:
    """Per-type weighted distribution over location kinds.

    Areas and Projects hit `topic`/`quest` location quirks; Resources
    almost always sit under `resources/`.
    """
    if type_ == "resource":
        return rng.choices(
            [LocationKind.PARA, LocationKind.TOPIC],
            weights=[0.85, 0.15],
            k=1,
        )[0]
    return rng.choices(
        [LocationKind.PARA, LocationKind.TOPIC, LocationKind.QUEST],
        weights=[0.6, 0.2, 0.2],
        k=1,
    )[0]


def _emit(
    out: Path,
    rel: Path,
    content: str,
    files: list[GeneratedFile],
    *,
    inputs: RenderInputs,
    location_kind: LocationKind,
) -> None:
    target = out / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        # Collisions happen when a Quest name collides with an Area name
        # in topic/quest layouts; tag them as DUPLICATE_TITLE rather than
        # overwriting silently.
        stem = target.stem
        suffix = 1
        while target.exists():
            target = target.with_name(f"{stem} ({suffix}){target.suffix}")
            suffix += 1
        rel = target.relative_to(out)
        inputs = RenderInputs(
            title=inputs.title,
            type_=inputs.type_,
            quest=inputs.quest,
            supports=inputs.supports,
            shape=Shape(
                location_kind=inputs.shape.location_kind,
                frontmatter_kind=inputs.shape.frontmatter_kind,
                quirks=inputs.shape.quirks | {Quirk.DUPLICATE_TITLE},
            ),
            extra_wikilinks=inputs.extra_wikilinks,
        )
    target.write_text(content, encoding="utf-8")
    files.append(
        GeneratedFile(
            path=rel.as_posix(),
            location_kind=location_kind,
            frontmatter_kind=inputs.shape.frontmatter_kind,
            quirks=tuple(sorted(inputs.shape.quirks, key=lambda q: q.value)),
            title=inputs.title,
            type_=inputs.type_,
        )
    )


def _attachment(faker: Faker) -> str:
    """Tiny placeholder sibling file."""
    return (
        "placeholder attachment generated by para-quest-notes corpus "
        f"generator\n{faker.sentence()}\n"
    )


def _maybe_emit_attachment(out: Path, sibling_rel: Path, faker: Faker) -> None:
    name = f"{sibling_rel.stem} attachment.txt"
    target = out / sibling_rel.parent / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_attachment(faker), encoding="utf-8")


def _related_resource_titles(seeds: Seeds, supports: Iterable[str]) -> tuple[str, ...]:
    """Resources whose `parents` overlap with this note's quests/areas
    are good wikilink targets for the body."""
    sup = set(supports)
    return tuple(r.title for r in seeds.resources if set(r.parents) & sup)


def generate_vault(
    out: Path,
    options: GenerateOptions | None = None,
    *,
    seeds_path: Path | None = None,
) -> GenerateResult:
    """Generate a sample vault under ``out``.

    Pure / deterministic for a given ``options.seed``. Returns a
    :class:`GenerateResult` describing what was produced.
    """
    options = options or GenerateOptions()
    seeds = load_seeds(seeds_path)
    out = Path(out).expanduser().resolve()
    _ensure_out_dir(out, options.clean)

    rng = random.Random(options.seed)
    faker = Faker()
    Faker.seed(options.seed)
    # Faker has its own internal RNG used by random_element, etc.
    # Faker.seed() seeds the class-level instance, which the per-instance
    # `faker.random` wraps.

    result = GenerateResult(out=out, options=options)

    # 1. Main and Side Quest notes — always emitted, always FULL backmatter
    #    (these are the spec-compliant anchors of the vault).
    for mq in seeds.main_quests:
        shape = Shape(
            location_kind=LocationKind.PARA,
            frontmatter_kind=FrontmatterKind.FULL,
            quirks=frozenset(),
        )
        inputs = inputs_for_main_quest(mq, shape)
        rel = Path("areas") / _filename(mq.name)
        _emit(
            out,
            rel,
            render_note(inputs, faker, seeds),
            result.files,
            inputs=inputs,
            location_kind=LocationKind.PARA,
        )

    for sq in seeds.side_quests:
        shape = Shape(
            location_kind=LocationKind.PARA,
            frontmatter_kind=FrontmatterKind.FULL,
            quirks=frozenset(),
        )
        inputs = inputs_for_side_quest(sq, shape)
        rel = Path("areas") / _filename(sq.name)
        _emit(
            out,
            rel,
            render_note(inputs, faker, seeds),
            result.files,
            inputs=inputs,
            location_kind=LocationKind.PARA,
        )

    # 2. Areas — either every Area in seeds.yaml (areas=0) or a sample.
    area_pool: list[AreaSeed] = list(seeds.areas)
    if options.areas > 0 and options.areas < len(area_pool):
        area_pool = rng.sample(area_pool, options.areas)
    for area in area_pool:
        loc = _location_for_seed_kind(rng, "area")
        shape = sample_shape(rng, loc, quirk_rate=options.quirk_rate)
        inputs = inputs_for_area(area, shape)
        rel = _path_for_inputs(inputs, faker=faker, seeds=seeds, location_kind=loc)
        _emit(
            out,
            rel,
            render_note(inputs, faker, seeds),
            result.files,
            inputs=inputs,
            location_kind=loc,
        )
        if shape.has(Quirk.HAS_ATTACHMENTS):
            _maybe_emit_attachment(out, rel, faker)

    # 3. Projects — sample to requested count (with replacement if the
    #    pool is small, so users can ask for more than seeds.yaml has).
    project_pool: list[ProjectSeed] = list(seeds.projects)
    if options.projects <= len(project_pool):
        chosen_projects = rng.sample(project_pool, options.projects)
    else:
        chosen_projects = list(project_pool) + [
            rng.choice(project_pool) for _ in range(options.projects - len(project_pool))
        ]
    for project in chosen_projects:
        loc = _location_for_seed_kind(rng, "project")
        shape = sample_shape(rng, loc, quirk_rate=options.quirk_rate)
        # Most Projects realistically have tasks; bias toward HAS_TASKS.
        if not shape.has(Quirk.HAS_TASKS) and rng.random() < 0.7:
            shape = Shape(
                location_kind=shape.location_kind,
                frontmatter_kind=shape.frontmatter_kind,
                quirks=shape.quirks | {Quirk.HAS_TASKS},
            )
        related = _related_resource_titles(seeds, project.supports)
        inputs = inputs_for_project(project, shape, extra_links=related)
        rel = _path_for_inputs(inputs, faker=faker, seeds=seeds, location_kind=loc)
        _emit(
            out,
            rel,
            render_note(inputs, faker, seeds),
            result.files,
            inputs=inputs,
            location_kind=loc,
        )
        if shape.has(Quirk.HAS_ATTACHMENTS):
            _maybe_emit_attachment(out, rel, faker)

    # 4. Resources — every one in seeds.yaml unless a count is set.
    resource_pool: list[ResourceSeed] = list(seeds.resources)
    if options.resources > 0 and options.resources < len(resource_pool):
        resource_pool = rng.sample(resource_pool, options.resources)
    for resource in resource_pool:
        loc = _location_for_seed_kind(rng, "resource")
        shape = sample_shape(rng, loc, quirk_rate=options.quirk_rate)
        inputs = inputs_for_resource(resource, shape)
        rel = _path_for_inputs(inputs, faker=faker, seeds=seeds, location_kind=loc)
        _emit(
            out,
            rel,
            render_note(inputs, faker, seeds),
            result.files,
            inputs=inputs,
            location_kind=loc,
        )

    # 5. Inbox notes — bare/messy, no Quest assignment yet.
    for _ in range(options.inbox):
        shape = sample_shape(rng, LocationKind.INBOX, quirk_rate=options.quirk_rate)
        title, content = render_inbox_note(faker, seeds, shape)
        inputs = RenderInputs(title=title, type_="resource", quest="none", supports=(), shape=shape)
        rel = Path("inbox") / _filename(title)
        _emit(out, rel, content, result.files, inputs=inputs, location_kind=LocationKind.INBOX)

    # 6. Daily notes — last N consecutive days from a seeded base date.
    base_date = dt.date(2026, 1, 1) + dt.timedelta(days=rng.randint(0, 60))
    for i in range(options.daily):
        d = base_date + dt.timedelta(days=i)
        shape = sample_shape(rng, LocationKind.DAILY, quirk_rate=options.quirk_rate)
        content = render_daily_note(faker, seeds, d, shape)
        inputs = RenderInputs(
            title=d.isoformat(),
            type_="resource",
            quest="none",
            supports=(),
            shape=shape,
        )
        rel = _daily_path(d)
        _emit(out, rel, content, result.files, inputs=inputs, location_kind=LocationKind.DAILY)

    if options.write_manifest:
        result.manifest_path.write_text(
            json.dumps(result.to_manifest_dict(), indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )

    return result


__all__ = [
    "DEFAULT_COUNTS",
    "GENERATOR_VERSION",
    "GeneratedFile",
    "GenerateOptions",
    "GenerateResult",
    "MANIFEST_FILENAME",
    "generate_vault",
]

"""Fixture loader for the eval harness.

Fixtures are hand-curated YAML files under ``eval/fixtures/``. Each
file holds either one fixture (a mapping with an ``id``) or a list of
them. Schema is intentionally small; see ``eval/fixtures/README.md``.

We validate on load and fail loudly. Eval signal is only as good as
the fixtures, and silent shape errors would degrade it invisibly.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from para_quest_notes.eval.registry import DEFAULT_WORKFLOW, get_workflow_eval, register_defaults

VALID_PARA_TYPES = ("project", "area", "resource")
VALID_QUEST_KINDS = ("main", "side")
_INGEST_STEPS = ("classify_para", "pick_quest", "propose_filename", "plan_destination")


class FixtureError(ValueError):
    """Raised when a fixture file is malformed."""


@dataclass(frozen=True)
class CatalogQuest:
    name: str
    kind: str  # "main" | "side"


@dataclass(frozen=True)
class ExpectedClassify:
    type: str  # one of VALID_PARA_TYPES


@dataclass(frozen=True)
class ExpectedPickQuest:
    """Expected Quest pick.

    ``acceptable`` is a list of acceptable quest-name sets - the pick
    passes if it equals any one of them. ``skipped`` covers resources
    where the workflow short-circuits.
    """

    acceptable: tuple[frozenset[str], ...] = ()
    skipped: bool = False


@dataclass(frozen=True)
class ExpectedFilename:
    canonical: str  # already canonicalized; see judges.canonical_filename


@dataclass(frozen=True)
class ExpectedDestination:
    destination: str  # vault-relative posix


@dataclass(frozen=True)
class Expected:
    classify_para: ExpectedClassify | None = None
    pick_quest: ExpectedPickQuest | None = None
    propose_filename: ExpectedFilename | None = None
    plan_destination: ExpectedDestination | None = None

    def has(self, step: str) -> bool:
        return getattr(self, step, None) is not None


@dataclass(frozen=True)
class Fixture:
    id: str
    title: str
    body: str
    quest_catalog: tuple[CatalogQuest, ...]
    expected: Expected
    frontmatter: dict[str, Any] = field(default_factory=dict)
    source: Path | None = None  # YAML file this came from
    workflow: str = DEFAULT_WORKFLOW


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def load_fixtures(path: Path) -> list[Any]:
    """Load fixtures from a file or directory of ``*.yaml`` / ``*.yml``."""
    register_defaults()
    p = Path(path)
    files = sorted(_iter_yaml_files(p)) if p.is_dir() else [p]

    seen_ids: set[str] = set()
    out: list[Any] = []
    for f in files:
        for fx in _load_one_file(f):
            if fx.id in seen_ids:
                raise FixtureError(f"duplicate fixture id {fx.id!r} (in {f})")
            seen_ids.add(fx.id)
            out.append(fx)
    return out


def _iter_yaml_files(directory: Path) -> Iterator[Path]:
    for p in directory.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".yaml", ".yml"):
            yield p


def _load_one_file(path: Path) -> list[Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FixtureError(f"{path}: failed to parse YAML: {exc}") from exc
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [_parse_fixture(raw, source=path)]
    if isinstance(raw, list):
        return [_parse_fixture(item, source=path) for item in raw]
    raise FixtureError(
        f"{path}: top level must be a mapping or a list of mappings, got {type(raw).__name__}"
    )


def _parse_fixture(raw: Any, *, source: Path) -> Any:
    if not isinstance(raw, dict):
        raise FixtureError(f"{source}: each fixture must be a mapping")
    workflow = raw.get("workflow", DEFAULT_WORKFLOW)
    if not isinstance(workflow, str) or not workflow.strip():
        raise FixtureError(f"{source}: 'workflow' must be a non-empty string when present")
    workflow = workflow.strip()
    try:
        loader = get_workflow_eval(workflow).fixture_loader
    except KeyError as exc:
        raise FixtureError(f"{source}: unknown workflow {workflow!r}") from exc
    fixture = loader(raw, source)
    if getattr(fixture, "workflow", workflow) != workflow:
        raise FixtureError(
            f"{source}: workflow loader for {workflow!r} returned fixture for "
            f"{getattr(fixture, 'workflow', None)!r}"
        )
    return fixture


def parse_ingest_fixture(raw: Any, source: Path) -> Fixture:
    if not isinstance(raw, dict):
        raise FixtureError(f"{source}: each fixture must be a mapping")
    fid = _require_str(raw, "id", source=source)
    title = _require_str(raw, "title", source=source)
    body = str(raw.get("body", ""))
    fm = raw.get("frontmatter") or {}
    if not isinstance(fm, dict):
        raise FixtureError(f"{source} ({fid}): 'frontmatter' must be a mapping")

    catalog = _parse_catalog(raw.get("quest_catalog") or [], source=source, fid=fid)
    expected = _parse_expected(raw.get("expected") or {}, source=source, fid=fid)

    if expected.pick_quest is not None and not expected.pick_quest.skipped and not catalog:
        raise FixtureError(f"{source} ({fid}): pick_quest expected but quest_catalog is empty")

    return Fixture(
        id=fid,
        title=title,
        body=body,
        quest_catalog=tuple(catalog),
        expected=expected,
        frontmatter=fm,
        source=source,
        workflow=DEFAULT_WORKFLOW,
    )


def _parse_catalog(items: Iterable[Any], *, source: Path, fid: str) -> list[CatalogQuest]:
    out: list[CatalogQuest] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise FixtureError(f"{source} ({fid}): quest_catalog entries must be mappings")
        name = _require_str(item, "name", source=source, ctx=f"{fid}.quest_catalog")
        kind = str(item.get("kind", "main")).strip()
        if kind not in VALID_QUEST_KINDS:
            raise FixtureError(f"{source} ({fid}): quest kind {kind!r} not in {VALID_QUEST_KINDS}")
        if name in seen:
            raise FixtureError(f"{source} ({fid}): duplicate quest {name!r} in catalog")
        seen.add(name)
        out.append(CatalogQuest(name=name, kind=kind))
    return out


def _parse_expected(raw: Any, *, source: Path, fid: str) -> Expected:
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): 'expected' must be a mapping")

    unknown = set(raw) - set(_INGEST_STEPS)
    if unknown:
        raise FixtureError(f"{source} ({fid}): expected has unknown step(s): {sorted(unknown)}")

    cp = _parse_classify(raw.get("classify_para"), source=source, fid=fid)
    pq = _parse_pick_quest(raw.get("pick_quest"), source=source, fid=fid)
    pf = _parse_filename(raw.get("propose_filename"), source=source, fid=fid)
    pd = _parse_destination(raw.get("plan_destination"), source=source, fid=fid)
    return Expected(
        classify_para=cp,
        pick_quest=pq,
        propose_filename=pf,
        plan_destination=pd,
    )


def _parse_classify(raw: Any, *, source: Path, fid: str) -> ExpectedClassify | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): expected.classify_para must be a mapping")
    t = _require_str(raw, "type", source=source, ctx=f"{fid}.classify_para")
    if t not in VALID_PARA_TYPES:
        raise FixtureError(f"{source} ({fid}): classify_para.type {t!r} not in {VALID_PARA_TYPES}")
    return ExpectedClassify(type=t)


def _parse_pick_quest(raw: Any, *, source: Path, fid: str) -> ExpectedPickQuest | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): expected.pick_quest must be a mapping")
    if raw.get("skipped"):
        return ExpectedPickQuest(skipped=True)
    acc_raw = raw.get("acceptable")
    if not isinstance(acc_raw, list) or not acc_raw:
        raise FixtureError(
            f"{source} ({fid}): pick_quest must declare 'skipped: true' "
            "or a non-empty 'acceptable' list of quest-name lists"
        )
    sets: list[frozenset[str]] = []
    for entry in acc_raw:
        if not isinstance(entry, list) or not all(isinstance(x, str) for x in entry):
            raise FixtureError(
                f"{source} ({fid}): pick_quest.acceptable entries must be lists of strings"
            )
        if not entry:
            raise FixtureError(f"{source} ({fid}): pick_quest.acceptable entries must be non-empty")
        sets.append(frozenset(entry))
    return ExpectedPickQuest(acceptable=tuple(sets))


def _parse_filename(raw: Any, *, source: Path, fid: str) -> ExpectedFilename | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): expected.propose_filename must be a mapping")
    canonical = _require_str(raw, "canonical", source=source, ctx=f"{fid}.propose_filename")
    return ExpectedFilename(canonical=canonical)


def _parse_destination(raw: Any, *, source: Path, fid: str) -> ExpectedDestination | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): expected.plan_destination must be a mapping")
    dest = _require_str(raw, "destination", source=source, ctx=f"{fid}.plan_destination")
    return ExpectedDestination(destination=dest)


def _require_str(raw: dict[str, Any], key: str, *, source: Path, ctx: str = "") -> str:
    if key not in raw:
        loc = f"{source} ({ctx})" if ctx else str(source)
        raise FixtureError(f"{loc}: missing required '{key}'")
    val = raw[key]
    if not isinstance(val, str) or not val.strip():
        loc = f"{source} ({ctx})" if ctx else str(source)
        raise FixtureError(f"{loc}: '{key}' must be a non-empty string")
    return val.strip()


__all__ = [
    "VALID_PARA_TYPES",
    "VALID_QUEST_KINDS",
    "CatalogQuest",
    "Expected",
    "ExpectedClassify",
    "ExpectedDestination",
    "ExpectedFilename",
    "ExpectedPickQuest",
    "Fixture",
    "FixtureError",
    "load_fixtures",
    "parse_ingest_fixture",
]

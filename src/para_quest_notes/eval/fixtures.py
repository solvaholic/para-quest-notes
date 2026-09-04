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
_ARCHIVE_STEPS = ("generate_outcome",)
_CREATE_STEPS = ("merge_template",)


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
    """Expected filename outcome.

    ``acceptable`` is a tuple of acceptable filename strings; the pick
    passes if its canonical form (see :func:`judges.canonical_filename`)
    matches any one of them. A fixture writes either a single
    ``canonical:`` string (the common "preserve the words" case) or an
    ``acceptable:`` list (upgrade-style fixtures where a few descriptive
    names are all valid).
    """

    acceptable: tuple[str, ...] = ()

    @property
    def canonical(self) -> str:
        """First acceptable value; back-compat for single-value callers."""
        return self.acceptable[0] if self.acceptable else ""


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
    # Explicit inbox source filename (the basename propose_filename sees).
    # When None, the harness falls back to ``inbox/<id>.md``.
    source_filename: str | None = None
    source: Path | None = None  # YAML file this came from
    workflow: str = DEFAULT_WORKFLOW


@dataclass(frozen=True)
class ArchiveInboundLink:
    basename: str
    snippet: str | None = None


@dataclass(frozen=True)
class ExpectedGenerateOutcome:
    keywords: tuple[str, ...] = ()
    text: str | None = None


@dataclass(frozen=True)
class ArchiveExpected:
    generate_outcome: ExpectedGenerateOutcome | None = None

    def has(self, step: str) -> bool:
        return getattr(self, step, None) is not None


@dataclass(frozen=True)
class ArchiveFixture:
    id: str
    title: str
    body: str
    completed_tasks: tuple[str, ...]
    inbound_links: tuple[ArchiveInboundLink, ...]
    expected: ArchiveExpected
    fake_response: str
    source: Path | None = None
    workflow: str = "archive"


@dataclass(frozen=True)
class ExpectedTemplateMerge:
    placements: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class CreateExpected:
    merge_template: ExpectedTemplateMerge | None = None

    def has(self, step: str) -> bool:
        return getattr(self, step, None) is not None


@dataclass(frozen=True)
class CreateFixture:
    id: str
    title: str
    template_name: str
    template: str
    stdin: str
    expected: CreateExpected
    source: Path | None = None
    workflow: str = "create"


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
    source_filename = _parse_source_filename(raw.get("source_filename"), source=source, fid=fid)

    if expected.pick_quest is not None and not expected.pick_quest.skipped and not catalog:
        raise FixtureError(f"{source} ({fid}): pick_quest expected but quest_catalog is empty")

    return Fixture(
        id=fid,
        title=title,
        body=body,
        quest_catalog=tuple(catalog),
        expected=expected,
        frontmatter=fm,
        source_filename=source_filename,
        source=source,
        workflow=DEFAULT_WORKFLOW,
    )


def parse_archive_fixture(raw: Any, source: Path) -> ArchiveFixture:
    if not isinstance(raw, dict):
        raise FixtureError(f"{source}: each fixture must be a mapping")
    fid = _require_str(raw, "id", source=source)
    title = _require_str(raw, "title", source=source)
    body = str(raw.get("body", ""))
    completed_tasks = _parse_string_list(raw.get("completed_tasks") or [], source=source, fid=fid)
    inbound_links = _parse_inbound_links(raw.get("inbound_links") or [], source=source, fid=fid)
    expected = _parse_archive_expected(raw.get("expected") or {}, source=source, fid=fid)
    fake_response = str(raw.get("fake_response", "")).strip()

    if expected.generate_outcome is not None and not fake_response:
        raise FixtureError(
            f"{source} ({fid}): archive fixtures with expected output need fake_response"
        )

    return ArchiveFixture(
        id=fid,
        title=title,
        body=body,
        completed_tasks=tuple(completed_tasks),
        inbound_links=tuple(inbound_links),
        expected=expected,
        fake_response=fake_response,
        source=source,
    )


def parse_create_fixture(raw: Any, source: Path) -> CreateFixture:
    if not isinstance(raw, dict):
        raise FixtureError(f"{source}: each fixture must be a mapping")
    fid = _require_str(raw, "id", source=source)
    title = _require_str(raw, "title", source=source)
    template_name = _require_str(raw, "template_name", source=source)
    template_path = Path(template_name)
    if (
        template_path.is_absolute()
        or template_name in (".", "..")
        or "/" in template_name
        or "\\" in template_name
    ):
        raise FixtureError(
            f"{source} ({fid}): 'template_name' must be a bare name without path segments"
        )
    template = _require_str(raw, "template", source=source)
    stdin = _require_str(raw, "stdin", source=source)
    expected = _parse_create_expected(raw.get("expected") or {}, source=source, fid=fid)
    return CreateFixture(
        id=fid,
        title=title,
        template_name=template_name,
        template=template,
        stdin=stdin,
        expected=expected,
        source=source,
    )


def _parse_source_filename(raw: Any, *, source: Path, fid: str) -> str | None:
    """Validate the optional explicit inbox source filename.

    A bare filename (no path separators). A missing ``.md`` extension is
    appended. Absent -> ``None`` (harness falls back to ``inbox/<id>.md``).
    """
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise FixtureError(f"{source} ({fid}): 'source_filename' must be a non-empty string")
    name = raw.strip()
    if "/" in name or "\\" in name:
        raise FixtureError(f"{source} ({fid}): 'source_filename' must not contain path separators")
    if not name.endswith(".md"):
        name = f"{name}.md"
    return name


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


def _parse_archive_expected(raw: Any, *, source: Path, fid: str) -> ArchiveExpected:
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): 'expected' must be a mapping")

    unknown = set(raw) - set(_ARCHIVE_STEPS)
    if unknown:
        raise FixtureError(f"{source} ({fid}): expected has unknown step(s): {sorted(unknown)}")

    return ArchiveExpected(
        generate_outcome=_parse_generate_outcome(
            raw.get("generate_outcome"), source=source, fid=fid
        ),
    )


def _parse_create_expected(raw: Any, *, source: Path, fid: str) -> CreateExpected:
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): 'expected' must be a mapping")
    unknown = set(raw) - set(_CREATE_STEPS)
    if unknown:
        raise FixtureError(f"{source} ({fid}): expected has unknown step(s): {sorted(unknown)}")
    return CreateExpected(
        merge_template=_parse_template_merge(
            raw.get("merge_template"),
            source=source,
            fid=fid,
        )
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
    has_canonical = "canonical" in raw
    has_acceptable = "acceptable" in raw
    if has_canonical == has_acceptable:
        raise FixtureError(
            f"{source} ({fid}): propose_filename must declare exactly one of "
            "'canonical' (a string) or 'acceptable' (a non-empty list of strings)"
        )
    if has_canonical:
        canonical = _require_str(raw, "canonical", source=source, ctx=f"{fid}.propose_filename")
        return ExpectedFilename(acceptable=(canonical,))
    acc_raw = raw.get("acceptable")
    if not isinstance(acc_raw, list) or not acc_raw:
        raise FixtureError(
            f"{source} ({fid}): propose_filename.acceptable must be a non-empty list of strings"
        )
    if not all(isinstance(x, str) and x.strip() for x in acc_raw):
        raise FixtureError(
            f"{source} ({fid}): propose_filename.acceptable entries must be non-empty strings"
        )
    return ExpectedFilename(acceptable=tuple(acc_raw))


def _parse_destination(raw: Any, *, source: Path, fid: str) -> ExpectedDestination | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): expected.plan_destination must be a mapping")
    dest = _require_str(raw, "destination", source=source, ctx=f"{fid}.plan_destination")
    return ExpectedDestination(destination=dest)


def _parse_generate_outcome(raw: Any, *, source: Path, fid: str) -> ExpectedGenerateOutcome | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): expected.generate_outcome must be a mapping")
    keywords = _parse_string_list(
        raw.get("keywords") or [],
        source=source,
        fid=f"{fid}.generate_outcome",
    )
    text = raw.get("text")
    if text is not None and (not isinstance(text, str) or not text.strip()):
        raise FixtureError(f"{source} ({fid}): expected.generate_outcome.text must be a string")
    if not keywords and text is None:
        raise FixtureError(
            f"{source} ({fid}): expected.generate_outcome needs 'keywords' and/or 'text'"
        )
    clean_text = text.strip() if isinstance(text, str) else None
    return ExpectedGenerateOutcome(keywords=tuple(keywords), text=clean_text)


def _parse_template_merge(
    raw: Any,
    *,
    source: Path,
    fid: str,
) -> ExpectedTemplateMerge | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise FixtureError(f"{source} ({fid}): expected.merge_template must be a mapping")
    unknown = set(raw) - {"placements"}
    if unknown:
        raise FixtureError(
            f"{source} ({fid}): expected.merge_template has unknown key(s): {sorted(unknown)}"
        )
    placements = raw.get("placements")
    if not isinstance(placements, dict) or not placements:
        raise FixtureError(
            f"{source} ({fid}): expected.merge_template.placements must be a non-empty mapping"
        )
    parsed: list[tuple[str, str]] = []
    for block_id, section_id in placements.items():
        if not isinstance(block_id, str) or not block_id.strip():
            raise FixtureError(
                f"{source} ({fid}): merge_template block IDs must be non-empty strings"
            )
        if not isinstance(section_id, str) or not section_id.strip():
            raise FixtureError(
                f"{source} ({fid}): merge_template section IDs must be non-empty strings"
            )
        parsed.append((block_id.strip(), section_id.strip()))
    return ExpectedTemplateMerge(placements=tuple(parsed))


def _parse_string_list(items: Iterable[Any], *, source: Path, fid: str) -> list[str]:
    out: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item.strip():
            raise FixtureError(f"{source} ({fid}): entries must be non-empty strings")
        out.append(item.strip())
    return out


def _parse_inbound_links(
    items: Iterable[Any],
    *,
    source: Path,
    fid: str,
) -> list[ArchiveInboundLink]:
    out: list[ArchiveInboundLink] = []
    for item in items:
        if isinstance(item, str):
            out.append(ArchiveInboundLink(basename=item.strip()))
            continue
        if not isinstance(item, dict):
            raise FixtureError(
                f"{source} ({fid}): inbound_links entries must be strings or mappings"
            )
        basename = _require_str(item, "basename", source=source, ctx=f"{fid}.inbound_links")
        snippet = item.get("snippet")
        if snippet is not None and (not isinstance(snippet, str) or not snippet.strip()):
            raise FixtureError(
                f"{source} ({fid}): inbound_links.snippet must be a non-empty string when present"
            )
        clean_snippet = snippet.strip() if snippet else None
        out.append(ArchiveInboundLink(basename=basename, snippet=clean_snippet))
    return out


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
    "ArchiveExpected",
    "ArchiveFixture",
    "ArchiveInboundLink",
    "CatalogQuest",
    "CreateExpected",
    "CreateFixture",
    "Expected",
    "ExpectedClassify",
    "ExpectedDestination",
    "ExpectedFilename",
    "ExpectedGenerateOutcome",
    "ExpectedPickQuest",
    "ExpectedTemplateMerge",
    "Fixture",
    "FixtureError",
    "load_fixtures",
    "parse_archive_fixture",
    "parse_create_fixture",
    "parse_ingest_fixture",
]

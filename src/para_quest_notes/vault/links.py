"""Vault wikilink parsing, backlink indexing, and one-pass note graphs.

The first of the link-aware building blocks. Lifted out of
``ingest_inbox/steps/apply_move.py`` (``_WIKILINK`` / ``_scan_wikilinks``)
so every link-aware CLI shares one wikilink parser and one backlink scan:

* ``pqn-quests`` (#86) surfaces Resources via incoming Area/Project links.
* ``pqn-search`` (#82) ranks Resources by incoming-link count.
* ``pqn-search --links`` (#138) traverses direct outgoing links and backlinks.

Unqualified wikilinks resolve by **basename**, case-insensitively - matching
Obsidian's resolver and most single-user vault filesystems. Anchors and aliases
do not change identity. Path-qualified wikilinks resolve the exact
vault-relative note in the identity-safe graph. The compatibility backlink
helpers retain their historical target normalization.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal, TypeAlias

# Capture group 1 is the link target (the note basename). Anchors (``#...``)
# and aliases (``|...``) are captured separately so callers can rewrite links
# without losing them.
WIKILINK = re.compile(r"\[\[([^\[\]|#]+?)(#[^\[\]|]+?)?(\|[^\[\]]+?)?\]\]")


def _normalize(stem: str) -> str:
    """Normalize a link target for case-insensitive basename matching."""
    return stem.strip().lower()


LinkTargetErrorKind: TypeAlias = Literal[
    "empty",
    "outside_vault",
    "missing",
    "ambiguous",
]
UnresolvedReason: TypeAlias = Literal["missing", "ambiguous"]


class LinkTargetError(ValueError):
    """A requested note target could not be resolved safely and uniquely."""

    def __init__(
        self,
        kind: LinkTargetErrorKind,
        target: str,
        *,
        candidates: Iterable[str] = (),
    ) -> None:
        self.kind = kind
        self.target = target
        self.candidates = tuple(candidates)
        super().__init__(self._message())

    def _message(self) -> str:
        if self.kind == "empty":
            return "link target is empty"
        if self.kind == "outside_vault":
            return "link target must be a vault-relative Markdown path inside the vault"
        if self.kind == "ambiguous":
            choices = ", ".join(self.candidates)
            return f"multiple notes match {self.target!r}; pass a vault-relative path" + (
                f": {choices}" if choices else ""
            )
        return f"no note found matching {self.target!r}"


@dataclass(frozen=True)
class LinkNote:
    """One readable note in a graph, keyed by vault-relative POSIX path."""

    path: Path
    relative_path: str
    stem: str
    text: str


@dataclass(frozen=True)
class LinkEdge:
    """One resolved directed edge and its occurrence count."""

    source: LinkNote
    target: LinkNote
    occurrences: int


@dataclass(frozen=True)
class UnresolvedGraphLink:
    """One missing or ambiguous outgoing target from a graph note."""

    target: str
    occurrences: int
    reason: UnresolvedReason
    candidates: tuple[str, ...] = ()


@dataclass
class LinkGraph:
    """Identity-safe in-memory graph built from an explicit file set."""

    vault: Path
    _notes_by_path: dict[str, LinkNote] = field(default_factory=dict)
    _paths_by_normalized_path: dict[str, tuple[str, ...]] = field(default_factory=dict)
    _paths_by_folded_path: dict[str, tuple[str, ...]] = field(default_factory=dict)
    _paths_by_stem: dict[str, tuple[str, ...]] = field(default_factory=dict)
    _outgoing: dict[str, dict[str, int]] = field(default_factory=dict)
    _incoming: dict[str, dict[str, int]] = field(default_factory=dict)
    _unresolved: dict[str, tuple[UnresolvedGraphLink, ...]] = field(default_factory=dict)

    @property
    def notes(self) -> tuple[LinkNote, ...]:
        """Every readable note, ordered by vault-relative path."""
        return tuple(self._notes_by_path[path] for path in sorted(self._notes_by_path))

    def note_at(self, relative_path: str) -> LinkNote:
        """Return one note by its exact vault-relative POSIX path."""
        return self._notes_by_path[relative_path]

    def resolve_target(self, target: str) -> LinkNote:
        """Resolve a vault-relative path or case-insensitive basename."""
        candidate = target.strip()
        if not candidate:
            raise LinkTargetError("empty", target)

        normalized_candidate = candidate.replace("\\", "/")
        parsed = PurePosixPath(normalized_candidate)
        if (
            Path(candidate).is_absolute()
            or PureWindowsPath(candidate).is_absolute()
            or parsed.is_absolute()
            or ".." in parsed.parts
        ):
            raise LinkTargetError("outside_vault", target)

        if normalized_candidate.lower().endswith(".md"):
            path_matches = _path_matches(
                parsed.as_posix(),
                notes_by_path=self._notes_by_path,
                paths_by_normalized_path=self._paths_by_normalized_path,
                paths_by_folded_path=self._paths_by_folded_path,
            )
            if len(path_matches) == 1:
                return self._notes_by_path[path_matches[0]]
            if len(path_matches) > 1:
                raise LinkTargetError("ambiguous", target, candidates=path_matches)
            if "/" in normalized_candidate:
                raise LinkTargetError("missing", target)
        elif "/" in normalized_candidate:
            raise LinkTargetError("missing", target)

        stem = candidate[:-3] if candidate.lower().endswith(".md") else candidate
        matches = self._paths_by_stem.get(_graph_target_key(stem), ())
        if not matches:
            raise LinkTargetError("missing", target)
        if len(matches) > 1:
            raise LinkTargetError("ambiguous", target, candidates=matches)
        return self._notes_by_path[matches[0]]

    def outgoing_from(self, note: LinkNote) -> tuple[LinkEdge, ...]:
        """Resolved outgoing edges from ``note``, ordered by target path."""
        return tuple(
            LinkEdge(
                source=note,
                target=self._notes_by_path[target_path],
                occurrences=occurrences,
            )
            for target_path, occurrences in sorted(
                self._outgoing.get(note.relative_path, {}).items()
            )
        )

    def incoming_to(self, note: LinkNote) -> tuple[LinkEdge, ...]:
        """Resolved incoming edges to ``note``, ordered by source path."""
        return tuple(
            LinkEdge(
                source=self._notes_by_path[source_path],
                target=note,
                occurrences=occurrences,
            )
            for source_path, occurrences in sorted(
                self._incoming.get(note.relative_path, {}).items()
            )
        )

    def unresolved_from(self, note: LinkNote) -> tuple[UnresolvedGraphLink, ...]:
        """Missing or ambiguous outgoing targets written in ``note``."""
        return self._unresolved.get(note.relative_path, ())


def _graph_target_display(target: str) -> str:
    """Normalize a wikilink target while preserving its first spelling."""
    raw = target.strip().replace("\\", "/")
    if not raw:
        return ""
    cleaned = PurePosixPath(raw).as_posix()
    return cleaned[:-3] if cleaned.lower().endswith(".md") else cleaned


def _canonical(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _graph_target_key(target: str) -> str:
    return _canonical(_graph_target_display(target).rsplit("/", 1)[-1])


def _graph_normalized_path(path: str) -> str:
    return unicodedata.normalize(
        "NFC",
        PurePosixPath(path.replace("\\", "/")).as_posix(),
    )


def _graph_path_key(path: str) -> str:
    return _graph_normalized_path(path).casefold()


def _path_matches(
    relative_path: str,
    *,
    notes_by_path: dict[str, LinkNote],
    paths_by_normalized_path: dict[str, tuple[str, ...]],
    paths_by_folded_path: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Resolve a path exact-first, then by canonical unique fallback."""
    if relative_path in notes_by_path:
        return (relative_path,)
    normalized = paths_by_normalized_path.get(
        _graph_normalized_path(relative_path),
        (),
    )
    if normalized:
        return normalized
    return paths_by_folded_path.get(_graph_path_key(relative_path), ())


def _graph_link_key(target: str) -> tuple[str, str, str]:
    """Return ``(kind, key, display)`` for one parsed wikilink target."""
    cleaned = target.strip().replace("\\", "/")
    parsed = PurePosixPath(cleaned)
    display = _graph_target_display(cleaned)
    if "/" not in cleaned:
        return "stem", _graph_target_key(cleaned), display
    if parsed.is_absolute() or ".." in parsed.parts:
        return "invalid", _canonical(display), display
    relative_path = parsed.as_posix()
    if not relative_path.lower().endswith(".md"):
        relative_path = f"{relative_path}.md"
    return "path", relative_path, display


def build_link_graph(vault: Path, files: Iterable[Path]) -> LinkGraph:
    """Read each candidate at most once and build an identity-safe link graph.

    The caller owns the file universe, including archive and exclusion policy.
    Unreadable files and candidates resolving outside ``vault`` are skipped.
    """
    vault_absolute = vault.absolute()
    vault_resolved = vault.resolve()
    notes_by_path: dict[str, LinkNote] = {}

    candidates: list[tuple[str, Path]] = []
    seen_paths: set[str] = set()
    for raw_path in files:
        if raw_path.is_absolute():
            candidate = raw_path
        else:
            from_cwd = raw_path.absolute()
            try:
                from_cwd.relative_to(vault_absolute)
            except ValueError:
                candidate = vault_absolute / raw_path
            else:
                candidate = from_cwd
        candidate = candidate.absolute()
        try:
            resolved_relative = candidate.resolve().relative_to(vault_resolved)
        except (OSError, ValueError):
            continue
        try:
            relative = candidate.relative_to(vault_absolute)
        except ValueError:
            relative = resolved_relative
        relative_path = relative.as_posix()
        if relative_path in seen_paths:
            continue
        seen_paths.add(relative_path)
        candidates.append((relative_path, vault_absolute / relative))

    for relative_path, candidate in sorted(candidates):
        try:
            text = candidate.read_text(encoding="utf-8")
        except OSError:
            continue
        notes_by_path[relative_path] = LinkNote(
            path=candidate,
            relative_path=relative_path,
            stem=candidate.stem,
            text=text,
        )

    paths_by_stem_lists: dict[str, list[str]] = {}
    for note in notes_by_path.values():
        paths_by_stem_lists.setdefault(_graph_target_key(note.stem), []).append(note.relative_path)
    paths_by_stem = {stem: tuple(sorted(paths)) for stem, paths in paths_by_stem_lists.items()}
    paths_by_normalized_lists: dict[str, list[str]] = {}
    paths_by_folded_lists: dict[str, list[str]] = {}
    for relative_path in notes_by_path:
        paths_by_normalized_lists.setdefault(
            _graph_normalized_path(relative_path),
            [],
        ).append(relative_path)
        paths_by_folded_lists.setdefault(_graph_path_key(relative_path), []).append(relative_path)
    paths_by_normalized_path = {
        path_key: tuple(sorted(paths)) for path_key, paths in paths_by_normalized_lists.items()
    }
    paths_by_folded_path = {
        path_key: tuple(sorted(paths)) for path_key, paths in paths_by_folded_lists.items()
    }

    outgoing: dict[str, dict[str, int]] = {}
    incoming: dict[str, dict[str, int]] = {}
    unresolved: dict[str, tuple[UnresolvedGraphLink, ...]] = {}

    for source in notes_by_path.values():
        counts: Counter[tuple[str, str]] = Counter()
        display_by_key: dict[tuple[str, str], str] = {}
        for raw_target in link_targets(source.text):
            kind, key, display = _graph_link_key(raw_target)
            if not key:
                continue
            identity = (kind, key)
            counts[identity] += 1
            display_by_key.setdefault(identity, display)

        unresolved_items: list[UnresolvedGraphLink] = []
        for identity, occurrences in counts.items():
            kind, key = identity
            matches = (
                _path_matches(
                    key,
                    notes_by_path=notes_by_path,
                    paths_by_normalized_path=paths_by_normalized_path,
                    paths_by_folded_path=paths_by_folded_path,
                )
                if kind == "path"
                else paths_by_stem.get(key, ())
                if kind == "stem"
                else ()
            )
            if len(matches) == 1:
                target_path = matches[0]
                source_edges = outgoing.setdefault(source.relative_path, {})
                source_edges[target_path] = source_edges.get(target_path, 0) + occurrences
                target_edges = incoming.setdefault(target_path, {})
                target_edges[source.relative_path] = (
                    target_edges.get(source.relative_path, 0) + occurrences
                )
                continue
            unresolved_items.append(
                UnresolvedGraphLink(
                    target=display_by_key[identity],
                    occurrences=occurrences,
                    reason="missing" if not matches else "ambiguous",
                    candidates=matches,
                )
            )
        unresolved[source.relative_path] = tuple(
            sorted(unresolved_items, key=lambda item: (item.target.lower(), item.target))
        )

    return LinkGraph(
        vault=vault_absolute,
        _notes_by_path=notes_by_path,
        _paths_by_normalized_path=paths_by_normalized_path,
        _paths_by_folded_path=paths_by_folded_path,
        _paths_by_stem=paths_by_stem,
        _outgoing=outgoing,
        _incoming=incoming,
        _unresolved=unresolved,
    )


def iter_markdown(vault: Path, *, include_archive: bool = False) -> list[Path]:
    """Return ``*.md`` files under ``vault``, excluding ``archive/`` by default.

    Deliberately minimal (archive-only exclusion) to preserve the historical
    behavior of ``apply_move``'s wikilink scan. Callers that need richer
    exclusions (``.git``, ``inbox/`` …) build their own file list and hand it
    to :func:`build_backlink_index`.
    """
    out: list[Path] = []
    for p in vault.rglob("*.md"):
        rel = p.relative_to(vault).parts
        if not include_archive and rel and rel[0] == "archive":
            continue
        out.append(p)
    return out


def link_targets(text: str) -> list[str]:
    """Return every wikilink target basename in ``text`` (order preserved)."""
    return [m.group(1).strip() for m in WIKILINK.finditer(text)]


def scan_backlinks(
    vault: Path,
    target_stem: str,
    *,
    exclude: Path | None = None,
    include_archive: bool = False,
) -> list[dict[str, Any]]:
    """Report notes that link to ``target_stem``, with occurrence counts.

    Returns ``[{"file": <vault-relative posix>, "occurrences": <int>}]`` for
    each note containing at least one wikilink to ``target_stem`` (matched by
    basename, case-insensitively). ``exclude`` skips one note (e.g. the note
    being renamed). This is the shape ``apply_move`` reports in dry-run.
    """
    target = _normalize(target_stem)
    exclude_resolved = exclude.resolve() if exclude is not None else None
    hits: list[dict[str, Any]] = []
    for md in iter_markdown(vault, include_archive=include_archive):
        if exclude_resolved is not None and md.resolve() == exclude_resolved:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        count = sum(1 for m in WIKILINK.finditer(text) if _normalize(m.group(1)) == target)
        if count:
            hits.append({"file": md.relative_to(vault).as_posix(), "occurrences": count})
    return hits


@dataclass(frozen=True)
class Backlink:
    """One note linking to a target, with how many times it does so."""

    source: Path
    occurrences: int


@dataclass
class BacklinkIndex:
    """Which notes link to a given note, keyed by normalized basename.

    Built once from a file list, then queried repeatedly. Cheaper than
    re-scanning the vault per target, which matters for a whole-vault index.
    """

    _by_target: dict[str, list[Backlink]] = field(default_factory=dict)

    def sources_for(self, target_stem: str) -> list[Backlink]:
        """Return the backlinks pointing at ``target_stem`` (basename match)."""
        return self._by_target.get(_normalize(target_stem), [])


def build_backlink_index(files: Iterable[Path]) -> BacklinkIndex:
    """Build a :class:`BacklinkIndex` from an explicit set of note paths.

    The caller controls the file set (and thus which notes count as link
    *sources*) — pass only active notes to exclude ``archive/``, drop
    ``inbox/``, and so on. Targets are keyed by normalized basename, so a
    link resolves to any note sharing that basename (validate flags the
    ambiguity separately).
    """
    index = BacklinkIndex()
    for md in files:
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        counts: Counter[str] = Counter(_normalize(t) for t in link_targets(text))
        for target, occurrences in counts.items():
            index._by_target.setdefault(target, []).append(
                Backlink(source=md, occurrences=occurrences)
            )
    return index

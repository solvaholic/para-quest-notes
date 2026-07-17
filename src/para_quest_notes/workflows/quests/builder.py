"""Build the Quest index from a vault walk.

Read-only, no LLM. Walks the vault, classifies each note by PARA type and
Quest association, and produces a flat :class:`QuestIndex` the CLI renders
as markdown or JSON.

Grouping rules (see ``docs/notes-system.md`` "Quest index" and issue #86):

* **Areas / Projects** roll up under each declared Quest in their
  ``supports:`` list.
* **Capabilities** (Areas with ``capability: true``) get their own section
  rather than being duplicated under every Quest they touch.
* **Resources** are surfaced via **incoming wikilinks from active (non-
  archived) Areas/Projects** — never from their own ``supports:`` and never
  from daily notes (a settled decision: daily-note links are usage *weight*,
  not Quest *assignment*). A Resource rolls up under the union of its
  linkers' Quests.
* **Unassigned** collects Areas/Projects with no ``supports:`` and Resources
  that roll up to no Quest, so they can be triaged.

Scope excludes ``inbox/`` (pre-PARA staging, owned by ``pqn-ingest``) and
``resources/daily_notes/`` (activity log, not a reference Resource) always;
``archive/`` is excluded unless ``include_archive`` is set.
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.vault.frontmatter import split_note
from para_quest_notes.vault.links import BacklinkIndex, build_backlink_index
from para_quest_notes.vault.quests import discover_quests
from para_quest_notes.vault.scope import Scope, note_supports, para_type_of
from para_quest_notes.workflows.validate.pipeline import list_markdown_files

from .contract import NoteEntry, QuestIndex, QuestRef

# Top-level dirs that never belong in the Quest index.
_INBOX_DIR = "inbox"
_DAILY_NOTES_PREFIX = ("resources", "daily_notes")


class _NoteInfo:
    """Everything the builder needs about one scanned note."""

    __slots__ = ("path", "rel", "stem", "type", "quest_kind", "supports", "capability", "archived")

    def __init__(
        self,
        *,
        path: Path,
        rel: str,
        stem: str,
        para_type: str | None,
        quest_kind: str,
        supports: list[str],
        capability: bool,
        archived: bool,
    ) -> None:
        self.path = path
        self.rel = rel
        self.stem = stem
        self.type = para_type
        self.quest_kind = quest_kind
        self.supports = supports
        self.capability = capability
        self.archived = archived


def _is_excluded(rel_parts: tuple[str, ...]) -> bool:
    """True for notes never included in the index (inbox, daily notes)."""
    parts = rel_parts
    if parts and parts[0] == "archive":
        parts = parts[1:]
    if parts and parts[0] == _INBOX_DIR:
        return True
    return parts[: len(_DAILY_NOTES_PREFIX)] == _DAILY_NOTES_PREFIX


def _scan_notes(vault: Path, *, include_archive: bool) -> list[_NoteInfo]:
    notes: list[_NoteInfo] = []
    for md in list_markdown_files(vault, include_archive=include_archive):
        rel_parts = md.relative_to(vault).parts
        if _is_excluded(rel_parts):
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        split = split_note(text)
        meta: dict[str, object] = {**split.backmatter, **split.frontmatter}
        quest_kind = meta.get("quest")
        quest_kind = quest_kind if quest_kind in ("main", "side") else "none"
        notes.append(
            _NoteInfo(
                path=md,
                rel=md.relative_to(vault).as_posix(),
                stem=md.stem,
                para_type=para_type_of(vault, md, meta),
                quest_kind=str(quest_kind),
                supports=note_supports(meta),
                capability=meta.get("capability") is True,
                archived=bool(rel_parts) and rel_parts[0] == "archive",
            )
        )
    return notes


def _resource_quests(
    resource: _NoteInfo,
    backlinks: BacklinkIndex,
    ap_by_path: dict[Path, _NoteInfo],
    quest_names: set[str],
) -> list[str]:
    """Quests a Resource rolls up under, via active Area/Project backlinks.

    Only **active** (non-archived) Areas/Projects confer assignment. A
    Resource with no such linker — or one linked only by Quest-less
    Areas/Projects — rolls up to nothing and lands in Unassigned.
    """
    rolled: list[str] = []
    seen: set[str] = set()
    for backlink in backlinks.sources_for(resource.stem):
        linker = ap_by_path.get(backlink.source)
        if linker is None or linker.archived:
            continue
        if linker.type not in ("area", "project"):
            continue
        for quest in linker.supports:
            key = quest.lower()
            if key in quest_names and key not in seen:
                seen.add(key)
                rolled.append(quest)
    return rolled


def build_quest_index(
    vault: Path,
    *,
    types: list[str] | None = None,
    quest: str | None = None,
    include_archive: bool = False,
) -> QuestIndex:
    """Walk ``vault`` and return the flat :class:`QuestIndex`.

    ``types`` is an include-only PARA-type allow-list (``--type``); ``quest``
    restricts to a single Quest (``--quest``); ``include_archive`` pulls in
    ``archive/``.
    """
    scope = Scope.from_args(types=types, quest=quest)
    declared = discover_quests(vault)
    quest_refs = [QuestRef(name=q.name, quest_kind=q.quest_kind) for q in declared]
    quest_names = {q.name.lower() for q in declared}

    notes = _scan_notes(vault, include_archive=include_archive)

    # Backlink sources are the active Areas/Projects among scanned notes.
    active_ap = [n for n in notes if n.type in ("area", "project") and not n.archived]
    ap_by_path = {n.path: n for n in active_ap}
    backlinks = build_backlink_index(n.path for n in active_ap)

    entries: list[NoteEntry] = []
    for note in notes:
        if not scope.allows_type(note.type):
            continue

        if note.type == "resource":
            rolled = _resource_quests(note, backlinks, ap_by_path, quest_names)
            unassigned = not rolled
            # A Resource's ``supports`` is not used for assignment; keep the
            # roll-up under ``quests`` and honor the quest filter against it.
            if not scope.matches_quest(rolled):
                continue
            entries.append(
                NoteEntry(
                    path=note.rel,
                    title=note.stem,
                    type=note.type,
                    quest=note.quest_kind,
                    supports=list(note.supports),
                    quests=rolled,
                    unassigned=unassigned,
                    archived=note.archived,
                )
            )
            continue

        if note.type in ("area", "project"):
            if not scope.matches_quest(note.supports):
                continue
            # Capabilities live in their own section, not under Quest groups.
            if note.capability and note.type == "area":
                entries.append(
                    NoteEntry(
                        path=note.rel,
                        title=note.stem,
                        type=note.type,
                        quest=note.quest_kind,
                        supports=list(note.supports),
                        quests=[],
                        capability=True,
                        archived=note.archived,
                    )
                )
                continue
            rolled = [s for s in note.supports if s.lower() in quest_names]
            entries.append(
                NoteEntry(
                    path=note.rel,
                    title=note.stem,
                    type=note.type,
                    quest=note.quest_kind,
                    supports=list(note.supports),
                    quests=rolled,
                    unassigned=not note.supports,
                    archived=note.archived,
                )
            )
            continue

        # Untyped note (no frontmatter type, not under a PARA dir): skip.

    entries.sort(key=lambda e: (e.title.lower(), e.path))

    return QuestIndex(
        vault=str(vault),
        scope={
            "types": sorted(scope.types) if scope.types is not None else None,
            "quest": scope.quest,
            "include_archive": include_archive,
        },
        quests=quest_refs,
        notes=entries,
    )

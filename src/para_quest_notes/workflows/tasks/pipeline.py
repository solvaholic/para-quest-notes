"""Scan a vault and report open tasks with Obsidian Tasks dates.

Read-only, no LLM. The pipeline is deliberately dumb (mirrors
``pqn-validate``): walk the markdown files, scan each for tasks via the
shared :mod:`para_quest_notes.vault.tasks` scanner, keep the open ones
that carry a tracked date, bucket them by urgency relative to a
reference date, and derive Quest/Area grouping keys from each note's
``supports:`` frontmatter.

Each task is bucketed on a single **effective date**: the first present
date in a configurable precedence over Obsidian Tasks' three emoji
fields — ``📅`` due, ``⏳`` scheduled, ``🛫`` start. Because the
resolution falls through, a user who only sets one kind of date (e.g.
``⏳`` scheduled as their "do date") is fully served without any
configuration; precedence only disambiguates a task that carries
several dates. A task with no tracked date is not reported. Done
(``[x]``) and cancelled (``[-]``) tasks are never reported.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

from para_quest_notes.vault.frontmatter import parse
from para_quest_notes.vault.quests import Quest, discover_quests
from para_quest_notes.vault.scope import Scope, note_supports, para_type_of
from para_quest_notes.vault.tasks import ScannedTask, scan_tasks

from .contract import DATE_FIELDS, Bucket, TaskItem, TasksReport

# Directories we never scan (matches pqn-validate's convention). ``archive/``
# is excluded too unless include_archive is set: archived tasks are
# completed/stale (pqn-archive rewrites open tasks to cancelled on archive).
_EXCLUDE_DIR_NAMES = {".git", ".obsidian", ".trash", "node_modules"}


def list_markdown_files(vault: Path, *, include_archive: bool = False) -> list[Path]:
    """Return all ``*.md`` files under ``vault`` in a deterministic order."""
    out: list[Path] = []
    for p in sorted(vault.rglob("*.md")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(vault).parts
        if any(part in _EXCLUDE_DIR_NAMES for part in rel_parts):
            continue
        if not include_archive and rel_parts and rel_parts[0] == "archive":
            continue
        out.append(p)
    return out


def _main_quests(name: str, by_name: dict[str, Quest], seen: set[str]) -> set[str]:
    """Resolve ``name`` up the supports graph to the Main Quest(s) it serves."""
    if name in seen:
        return set()
    seen.add(name)
    q = by_name.get(name)
    if q is None:
        return set()
    if q.quest_kind == "main":
        return {q.name}
    out: set[str] = set()
    for s in q.supports:
        out |= _main_quests(s, by_name, seen)
    return out


def _bucket_for(due: date, today: date, horizon: date) -> Bucket | None:
    """Return the bucket for ``due``, or None when outside the window."""
    if due < today:
        return "overdue"
    if due == today:
        return "due_today"
    if due <= horizon:
        return "upcoming"
    return None


def _effective_date(task: ScannedTask, date_fields: Sequence[str]) -> tuple[date, str] | None:
    """Return ``(date, field_name)`` for the first present tracked date.

    Iterates ``date_fields`` in precedence order and returns the first one
    the task actually carries. Returns None when the task has none of the
    tracked dates (it won't be reported).
    """
    for field_name in date_fields:
        value = getattr(task, field_name)
        if value is not None:
            return value, field_name
    return None


def scan_vault_tasks(
    vault: Path,
    *,
    today: date | None = None,
    due_in: int = 7,
    overdue_only: bool = False,
    types: Sequence[str] | None = None,
    quest: str | None = None,
    group_by: str = "due",
    date_fields: Sequence[str] | None = None,
    include_archive: bool = False,
) -> TasksReport:
    """Scan ``vault`` and return a :class:`TasksReport`.

    ``today`` defaults to the system date (injectable for tests).
    ``due_in`` sets the upcoming horizon in days. ``overdue_only`` keeps
    only tasks whose effective date is in the past. ``types`` is an
    include-only PARA-type allow-list; ``quest`` filters to notes whose
    ``supports:`` includes that Quest (wikilink or bare name, matched
    case-insensitively — identical semantics to ``pqn-quests``).
    ``date_fields`` is the ordered precedence over
    ``("due", "scheduled", "start")`` used to pick each task's effective
    (bucketing) date; a field omitted from the list is ignored entirely,
    so ``["scheduled"]`` reports scheduled-dated tasks only.
    """
    ref = today or date.today()
    horizon = ref + timedelta(days=due_in)
    scope = Scope.from_args(types=types, quest=quest)
    fields = list(date_fields) if date_fields else list(DATE_FIELDS)

    by_name = {q.name: q for q in discover_quests(vault)}

    files = list_markdown_files(vault, include_archive=include_archive)
    items: list[TaskItem] = []

    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        rel = path.relative_to(vault)
        parsed = parse(text)
        supports = note_supports(parsed.frontmatter)
        para_type = para_type_of(vault, path, parsed.frontmatter)

        if not scope.matches(para_type=para_type, supports=supports):
            continue

        is_area_note = bool(rel.parts) and rel.parts[0] == "areas"
        area_keys = [rel.stem] if is_area_note else list(supports)
        quest_keys = sorted({m for s in supports for m in _main_quests(s, by_name, set())})

        # File-line offset: body is the exact suffix parse() returns, so the
        # count of newlines before it is the number of lines above the body.
        line_offset = text.count("\n", 0, len(text) - len(parsed.body))

        for task in scan_tasks(parsed.body):
            if not task.is_open:
                continue
            resolved = _effective_date(task, fields)
            if resolved is None:
                continue
            eff_date, source = resolved
            bucket = _bucket_for(eff_date, ref, horizon)
            if bucket is None:
                continue
            if overdue_only and bucket != "overdue":
                continue
            items.append(
                TaskItem(
                    path=rel.as_posix(),
                    line=task.line + line_offset,
                    description=task.description,
                    raw=task.text,
                    state=task.state,
                    bucket=bucket,
                    effective_date=eff_date.isoformat(),
                    date_source=source,
                    due=task.due.isoformat() if task.due else None,
                    scheduled=task.scheduled.isoformat() if task.scheduled else None,
                    start=task.start.isoformat() if task.start else None,
                    block_id=task.block_id,
                    supports=list(supports),
                    areas=area_keys,
                    quests=quest_keys,
                )
            )

    items.sort(key=lambda t: (t.effective_date, t.path, t.line))

    return TasksReport(
        vault=str(vault),
        reference_date=ref.isoformat(),
        due_in=due_in,
        group_by=group_by,
        date_fields=fields,
        include_archive=include_archive,
        types=sorted(scope.types) if scope.types is not None else None,
        quest=scope.quest,
        files_scanned=len(files),
        tasks=items,
    )

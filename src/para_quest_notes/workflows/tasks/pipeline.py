"""Scan a vault and report open tasks with Obsidian Tasks due dates.

Read-only, no LLM. The pipeline is deliberately dumb (mirrors
``pqn-validate``): walk the markdown files, scan each for tasks via the
shared :mod:`para_quest_notes.vault.tasks` scanner, keep the open ones
that carry a ``📅`` due date, bucket them by urgency relative to a
reference date, and derive Quest/Area grouping keys from each note's
``supports:`` frontmatter.

Only tasks with a **due date** are reported. ``⏳`` scheduled and ``🛫``
start dates are parsed and surfaced as fields but are not (yet) a
bucketing axis — the report answers "what's due when". Done (``[x]``)
and cancelled (``[-]``) tasks are never reported.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from para_quest_notes.vault.frontmatter import parse
from para_quest_notes.vault.quests import Quest, discover_quests
from para_quest_notes.vault.tasks import scan_tasks

from .contract import Bucket, TaskItem, TasksReport

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


def _strip_wikilink(s: str) -> str:
    s = s.strip()
    if s.startswith("[[") and s.endswith("]]"):
        s = s[2:-2]
    if "|" in s:
        s = s.split("|", 1)[0]
    return s.strip()


def _supports_targets(frontmatter: dict[str, Any]) -> list[str]:
    raw = frontmatter.get("supports") or []
    if not isinstance(raw, list):
        raw = [raw]
    return [_strip_wikilink(str(s)) for s in raw if s]


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


def scan_vault_tasks(
    vault: Path,
    *,
    today: date | None = None,
    due_in: int = 7,
    overdue_only: bool = False,
    quest: str | None = None,
    group_by: str = "due",
    include_archive: bool = False,
) -> TasksReport:
    """Scan ``vault`` and return a :class:`TasksReport`.

    ``today`` defaults to the system date (injectable for tests).
    ``due_in`` sets the upcoming horizon in days. ``overdue_only`` keeps
    only tasks whose due date is in the past. ``quest`` filters to notes
    whose ``supports:`` includes that Quest (wikilink syntax tolerated).
    """
    ref = today or date.today()
    horizon = ref + timedelta(days=due_in)
    quest_filter = _strip_wikilink(quest) if quest else None

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
        supports = _supports_targets(parsed.frontmatter)

        if quest_filter is not None and quest_filter not in supports:
            continue

        is_area_note = bool(rel.parts) and rel.parts[0] == "areas"
        area_keys = [rel.stem] if is_area_note else list(supports)
        quest_keys = sorted({m for s in supports for m in _main_quests(s, by_name, set())})

        # File-line offset: body is the exact suffix parse() returns, so the
        # count of newlines before it is the number of lines above the body.
        line_offset = text.count("\n", 0, len(text) - len(parsed.body))

        for task in scan_tasks(parsed.body):
            if not task.is_open or task.due is None:
                continue
            bucket = _bucket_for(task.due, ref, horizon)
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
                    due=task.due.isoformat(),
                    scheduled=task.scheduled.isoformat() if task.scheduled else None,
                    start=task.start.isoformat() if task.start else None,
                    block_id=task.block_id,
                    supports=list(supports),
                    areas=area_keys,
                    quests=quest_keys,
                )
            )

    items.sort(key=lambda t: (t.due or "", t.path, t.line))

    return TasksReport(
        vault=str(vault),
        reference_date=ref.isoformat(),
        due_in=due_in,
        group_by=group_by,
        include_archive=include_archive,
        files_scanned=len(files),
        tasks=items,
    )

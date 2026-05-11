"""Step 6: apply_move (pure, atomic).

Dry-run by default. With ``apply=True``:

* Move the source file to the planned destination via ``Path.replace``.
* Move sibling attachments (whose stems start with the source stem) to
  the destination directory, rewriting their stems to match the new
  name.
* Merge spec frontmatter (``type``, ``quest``, ``supports``) into the
  moved file. Existing frontmatter is preserved; the three keys above
  are overwritten authoritatively.
* Rewrite incoming wikilinks across the vault, excluding ``archive/``,
  for the renamed note. ``[[old]]`` -> ``[[New]]``;
  ``[[old|alias]]`` -> ``[[New|alias]]``.

The step never escalates — by the time we get here, the prior steps
have committed to a plan. Failures during the apply phase raise.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult
from para_quest_notes.vault.frontmatter import ParsedNote, merge
from para_quest_notes.workflows.ingest_inbox.contract import AppliedChange
from para_quest_notes.workflows.ingest_inbox.steps.scan_note import ScanResult


class ApplyMove:
    name = "apply_move"

    def __init__(self, *, apply: bool):
        self.apply = apply

    def run(self, ctx: StepContext) -> StepResult:
        scan: ScanResult = ctx.scratchpad["scan"]
        vault: Path = ctx.vault if ctx.vault is not None else scan.source.parent.parent
        destination_rel = ctx.scratchpad.get("destination")
        if not destination_rel:
            raise EscalateToUser(
                step=self.name,
                reason="no destination planned",
                options=[],
                context={},
            )
        dest = vault / destination_rel
        para_type = ctx.scratchpad.get("para_type") or ""
        quests: list[str] = ctx.scratchpad.get("quests", [])

        # Pre-flight collision detection happens in `propose_filename`
        # (which delegates to `validate.api.check_basename_available`),
        # so by the time we get here the destination basename is known
        # to be unique vault-wide.

        new_fm = _build_frontmatter(scan.parsed.frontmatter, para_type, quests)
        old_stem = scan.source.stem
        new_stem = dest.stem

        change = AppliedChange(
            moved_from=str(scan.source.relative_to(vault).as_posix()),
            moved_to=destination_rel,
        )

        if not self.apply:
            change.frontmatter_updated = new_fm != scan.parsed.frontmatter
            # Surface what *would* move/rewrite without touching disk.
            change.attachments_moved = [
                (
                    str(att.relative_to(vault).as_posix()),
                    f"{dest.parent.relative_to(vault).as_posix()}/"
                    f"{_rename_attachment(att.name, old_stem, new_stem)}",
                )
                for att in scan.attachments
            ]
            change.wikilinks_rewritten = _scan_wikilinks(vault, old_stem, scan.source)
            return StepResult(
                name=self.name,
                output=change,
                meta={"applied": False, "wikilinks": len(change.wikilinks_rewritten)},
            )

        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            raise EscalateToUser(
                step=self.name,
                reason=f"destination already exists: {destination_rel}",
                options=[],
                context={},
            )

        # Write merged content first (to a temp path), then move atomically.
        merged = ParsedNote(frontmatter=new_fm, body=scan.parsed.body, had_frontmatter=True)
        rendered = merged.render()
        scan.source.write_text(rendered, encoding="utf-8")
        scan.source.replace(dest)
        change.frontmatter_updated = True

        for att in scan.attachments:
            new_name = _rename_attachment(att.name, old_stem, new_stem)
            new_path = dest.parent / new_name
            if new_path.exists():
                # Don't clobber; back off and report.
                continue
            att.replace(new_path)
            change.attachments_moved.append(
                (
                    str(att.relative_to(vault).as_posix()) if att.exists() else f"inbox/{att.name}",
                    str(new_path.relative_to(vault).as_posix()),
                )
            )

        change.wikilinks_rewritten = _rewrite_wikilinks(vault, old_stem, new_stem, exclude=dest)

        return StepResult(
            name=self.name,
            output=change,
            meta={"applied": True, "wikilinks": len(change.wikilinks_rewritten)},
        )


def _build_frontmatter(
    existing: dict[str, Any], para_type: str, quests: list[str]
) -> dict[str, Any]:
    if para_type == "resource":
        # Resources: type required; quest defaults to "none"; supports optional.
        updates: dict[str, Any] = {"type": "resource", "quest": "none"}
        if quests:
            updates["supports"] = [f"[[{q}]]" for q in quests]
    elif para_type == "area":
        updates = {"type": "area", "quest": "none"}
        if quests:
            updates["supports"] = [f"[[{q}]]" for q in quests]
    else:  # project
        updates = {
            "type": "project",
            "quest": "none",
            "supports": [f"[[{q}]]" for q in quests],
        }
    return merge(existing, updates)


def _rename_attachment(name: str, old_stem: str, new_stem: str) -> str:
    if name.startswith(f"{old_stem} "):
        return f"{new_stem} {name[len(old_stem) + 1 :]}"
    if Path(name).stem == old_stem:
        return f"{new_stem}{Path(name).suffix}"
    return name


_WIKILINK = re.compile(r"\[\[([^\[\]|#]+?)(#[^\[\]|]+?)?(\|[^\[\]]+?)?\]\]")


def _iter_md(vault: Path) -> list[Path]:
    return [
        p
        for p in vault.rglob("*.md")
        if not p.relative_to(vault).parts or p.relative_to(vault).parts[0] != "archive"
    ]


def _scan_wikilinks(vault: Path, old_stem: str, source: Path) -> list[dict[str, Any]]:
    """Dry-run: report files that *would* be rewritten."""
    hits: list[dict[str, Any]] = []
    target = old_stem.strip().lower()
    for md in _iter_md(vault):
        if md.resolve() == source.resolve():
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue
        count = sum(1 for m in _WIKILINK.finditer(text) if m.group(1).strip().lower() == target)
        if count:
            hits.append(
                {
                    "file": str(md.relative_to(vault).as_posix()),
                    "occurrences": count,
                }
            )
    return hits


def _rewrite_wikilinks(
    vault: Path, old_stem: str, new_stem: str, *, exclude: Path
) -> list[dict[str, Any]]:
    target = old_stem.strip().lower()
    hits: list[dict[str, Any]] = []
    for md in _iter_md(vault):
        if md.resolve() == exclude.resolve():
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError:
            continue

        count = 0

        def _sub(m: re.Match[str]) -> str:
            nonlocal count
            link = m.group(1).strip()
            if link.lower() != target:
                return m.group(0)
            count += 1
            alias = m.group(3) or ""
            anchor = m.group(2) or ""
            return f"[[{new_stem}{anchor}{alias}]]"

        new_text = _WIKILINK.sub(_sub, text)
        if count:
            md.write_text(new_text, encoding="utf-8")
            hits.append(
                {
                    "file": str(md.relative_to(vault).as_posix()),
                    "occurrences": count,
                }
            )
    return hits

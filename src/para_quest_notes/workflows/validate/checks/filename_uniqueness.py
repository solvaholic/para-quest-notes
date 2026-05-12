"""Detect duplicate basenames across the vault.

Two notes with the same filename in different directories make
``[[wikilinks]]`` ambiguous. This check is vault-wide by nature: the
``files`` argument is the *focus set* (what to report on) but the
collision index is always built from the entire vault.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from ..contract import ValidateIssue

ID = "filename_uniqueness"


def run(vault: Path, files: list[Path], all_md: list[Path]) -> list[ValidateIssue]:
    # Wikilink resolution in Obsidian (and on case-insensitive filesystems
    # like macOS/Windows defaults) ignores case, so collisions are
    # case-insensitive too.
    by_name: dict[str, list[Path]] = defaultdict(list)
    for p in all_md:
        by_name[p.name.lower()].append(p)

    # Focus paths that don't (yet) exist on disk — typically a planned
    # destination passed by ``validate_paths`` from another workflow —
    # are treated as hypothetical inserts so we can answer "would this
    # new note collide?" The synthetic entries are deduped against
    # ``all_md`` to avoid double-counting existing files.
    on_disk = {p.resolve() for p in all_md}
    for f in files:
        resolved = f.resolve() if f.exists() else f
        if resolved in on_disk:
            continue
        try:
            f.relative_to(vault)
        except ValueError:
            continue  # focus path outside the vault: ignore
        by_name[f.name.lower()].append(f)

    focus = {p.resolve() if p.exists() else p for p in files}
    issues: list[ValidateIssue] = []
    seen_groups: set[tuple[str, ...]] = set()

    def _rel(p: Path) -> str:
        try:
            return p.relative_to(vault).as_posix()
        except ValueError:
            return str(p)

    for paths in by_name.values():
        if len(paths) < 2:
            continue
        if focus and not any((p.resolve() if p.exists() else p) in focus for p in paths):
            continue
        rels = sorted(_rel(p) for p in paths)
        key = tuple(rels)
        if key in seen_groups:
            continue
        seen_groups.add(key)
        # Use the on-disk casing of the first occurrence as the
        # representative basename in the message.
        display_name = paths[0].name
        for rel in rels:
            others = [r for r in rels if r != rel]
            issues.append(
                ValidateIssue(
                    check=ID,
                    severity="error",
                    path=rel,
                    message=(
                        f"filename '{display_name}' is not unique in the vault "
                        f"({len(paths)} occurrences); "
                        "wikilinks to it will be ambiguous"
                    ),
                    related=others,
                    detail={"basename": display_name, "count": len(paths)},
                )
            )
    return issues

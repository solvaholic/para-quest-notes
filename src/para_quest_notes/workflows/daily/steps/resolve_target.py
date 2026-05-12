"""Step 1: resolve_target (pure).

Find the source daily-note file the user named. Accepts either a
vault-relative path, an absolute path inside the vault, or a bare
basename (with or without ``.md``). Basename search is scoped to the
only legal "loose" homes for a daily note: vault root, ``inbox/`` (any
depth), and ``resources/daily_notes/`` (any depth, for idempotent
re-filing).

Path-form targets are accepted regardless of subtree — ``inspect_parent``
is the gate that rejects daily notes living somewhere PARA-meaningful
(``projects/``, ``areas/``, ``archive/``, other ``resources/`` subtrees).
"""

from __future__ import annotations

from pathlib import Path

from para_quest_notes.adapter.errors import EscalateToUser
from para_quest_notes.adapter.step import StepContext, StepResult


class ResolveTarget:
    name = "resolve_target"

    def __init__(self, target: str):
        self.target = target

    def run(self, ctx: StepContext) -> StepResult:
        if ctx.vault is None:
            raise EscalateToUser(
                step=self.name,
                reason="no vault path resolved",
                options=[],
                context={},
            )
        vault = ctx.vault
        candidate = self.target.strip()
        if not candidate:
            raise EscalateToUser(
                step=self.name,
                reason="target is empty",
                options=[],
                context={},
            )

        # Path-form: input contains a separator or is absolute. Otherwise
        # treat as a bare basename and run the scoped search below — that
        # way ambiguity (same basename in two allowed locations) surfaces
        # instead of being silently resolved by a vault-root probe.
        as_path = Path(candidate)
        looks_like_path = "/" in candidate or as_path.is_absolute()
        if looks_like_path:
            probe = as_path if as_path.is_absolute() else vault / candidate
            if probe.is_file():
                return self._ok(ctx, probe, vault)
            raise EscalateToUser(
                step=self.name,
                reason=f"no file found at {self.target!r}",
                options=[],
                context={},
            )

        # Basename search, scoped to vault root + inbox/ + resources/daily_notes/.
        basename = candidate if candidate.endswith(".md") else f"{candidate}.md"

        matches: list[Path] = []
        # Vault root only (not recursive).
        root_hit = vault / basename
        if root_hit.is_file():
            matches.append(root_hit)
        # inbox/ (recursive).
        inbox = vault / "inbox"
        if inbox.is_dir():
            matches.extend(p for p in inbox.rglob(basename) if p.is_file())
        # resources/daily_notes/ (recursive) — for idempotent re-filing.
        daily_root = vault / "resources" / "daily_notes"
        if daily_root.is_dir():
            matches.extend(p for p in daily_root.rglob(basename) if p.is_file())

        # Deduplicate (a path could match the root hit and a glob).
        seen: set[Path] = set()
        unique: list[Path] = []
        for m in matches:
            r = m.resolve()
            if r in seen:
                continue
            seen.add(r)
            unique.append(m)

        if not unique:
            raise EscalateToUser(
                step=self.name,
                reason=f"no daily note found matching {self.target!r}",
                options=[],
                context={"searched": "vault root, inbox/, resources/daily_notes/"},
            )
        if len(unique) > 1:
            raise EscalateToUser(
                step=self.name,
                reason=f"multiple files match {self.target!r}; pass a path",
                options=[{"path": str(m.relative_to(vault).as_posix())} for m in unique],
                context={},
            )
        return self._ok(ctx, unique[0], vault)

    def _ok(self, ctx: StepContext, source: Path, vault: Path) -> StepResult:
        try:
            rel = source.resolve().relative_to(vault.resolve()).as_posix()
        except ValueError as exc:
            raise EscalateToUser(
                step=self.name,
                reason="target is outside the vault",
                options=[],
                context={"target": str(source)},
            ) from exc
        ctx.scratchpad["source_abs"] = source
        ctx.scratchpad["source_rel"] = rel
        return StepResult(
            name=self.name,
            output={"source": rel},
            meta={"source": rel},
        )

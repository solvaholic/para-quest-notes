"""Step 1: resolve_target (pure).

Find the Project note the user named. Accepts either a vault-relative
path (``projects/foo/X.md``), a bare path, or just a basename
(``X`` or ``X.md``). Searches under ``projects/`` only — Areas and
Resources aren't archivable in v1, so we don't even look there.
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
        projects_dir = vault / "projects"
        if not projects_dir.is_dir():
            raise EscalateToUser(
                step=self.name,
                reason="vault has no projects/ directory",
                options=[],
                context={"vault": str(vault)},
            )

        candidate = self.target.strip()
        if not candidate:
            raise EscalateToUser(
                step=self.name,
                reason="target is empty",
                options=[],
                context={},
            )

        # Strategy:
        # 1. If candidate looks like a path (contains '/' or already has
        #    .md and resolves relative to vault), try that first.
        # 2. Otherwise, glob under projects/ for the basename.
        # 3. Reject anything outside projects/.
        path_candidates: list[Path] = []
        as_path = Path(candidate)
        if as_path.is_absolute():
            path_candidates.append(as_path)
        else:
            path_candidates.append(vault / candidate)
            path_candidates.append(vault / "projects" / candidate)
            if not candidate.endswith(".md"):
                path_candidates.append(vault / "projects" / f"{candidate}.md")

        for p in path_candidates:
            if p.is_file():
                self._guard_under_projects(p, vault)
                return self._ok(ctx, p, vault)

        # Basename search under projects/.
        basename = candidate if candidate.endswith(".md") else f"{candidate}.md"
        matches = sorted(projects_dir.rglob(basename))
        # Exclude archive/ explicitly — projects_dir is already projects/
        # but be defensive about symlinks etc.
        matches = [m for m in matches if "archive" not in m.relative_to(vault).parts]
        if not matches:
            raise EscalateToUser(
                step=self.name,
                reason=f"no Project note found matching {self.target!r}",
                options=[],
                context={"searched": "projects/"},
            )
        if len(matches) > 1:
            raise EscalateToUser(
                step=self.name,
                reason=f"multiple Project notes match {self.target!r}; pass a path",
                options=[{"path": str(m.relative_to(vault).as_posix())} for m in matches],
                context={},
            )
        return self._ok(ctx, matches[0], vault)

    def _guard_under_projects(self, source: Path, vault: Path) -> None:
        try:
            rel = source.resolve().relative_to(vault.resolve())
        except ValueError as exc:
            raise EscalateToUser(
                step=self.name,
                reason="target is outside the vault",
                options=[],
                context={"target": str(source)},
            ) from exc
        parts = rel.parts
        if not parts or parts[0] != "projects":
            raise EscalateToUser(
                step=self.name,
                reason="pqn-archive v1 is Projects only "
                f"(target is under {parts[0] if parts else '/'}/)",
                options=[],
                context={"path": str(rel.as_posix())},
            )

    def _ok(self, ctx: StepContext, source: Path, vault: Path) -> StepResult:
        rel = source.resolve().relative_to(vault.resolve()).as_posix()
        ctx.scratchpad["source_abs"] = source
        ctx.scratchpad["source_rel"] = rel
        return StepResult(
            name=self.name,
            output={"source": rel},
            meta={"source": rel},
        )

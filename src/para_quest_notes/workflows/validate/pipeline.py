"""Run validate checks against a vault.

The pipeline is dumb on purpose: collect the file set, look up checks,
call each one, concatenate issues. No threads, no caching — vaults are
small (single-user note collections) and ``pqn-validate`` is read-only.
"""

from __future__ import annotations

from pathlib import Path

from .checks import ALL_CHECKS, CHECKS_BY_ID
from .contract import Severity, ValidateIssue, ValidateReport

# Directories we never scan. ``archive/`` follows the same convention as
# ingest: archived notes shouldn't be touched by routine maintenance
# (toggle with --include-archive when you really mean it).
_EXCLUDE_DIR_NAMES = {".git", ".obsidian", ".trash", "node_modules"}

_SEVERITY_RANK = {"info": 0, "warning": 1, "error": 2}


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


def run_pipeline(
    vault: Path,
    *,
    paths: list[Path] | None = None,
    checks: list[str] | None = None,
    min_severity: Severity = "warning",
    include_archive: bool = False,
) -> ValidateReport:
    all_md = list_markdown_files(vault, include_archive=include_archive)
    focus = all_md if paths is None else [_resolve(vault, p) for p in paths]

    if checks is None:
        selected = list(ALL_CHECKS)
    else:
        try:
            selected = [CHECKS_BY_ID[c] for c in checks]
        except KeyError as exc:
            raise ValueError(f"unknown check: {exc.args[0]}") from None

    issues: list[ValidateIssue] = []
    for check in selected:
        issues.extend(check.run(vault, focus, all_md))

    threshold = _SEVERITY_RANK[min_severity]
    issues = [i for i in issues if _SEVERITY_RANK[i.severity] >= threshold]
    issues.sort(key=lambda i: (-_SEVERITY_RANK[i.severity], i.path, i.check))

    return ValidateReport(
        vault=str(vault),
        files_scanned=len(focus),
        checks_run=[c.ID for c in selected],
        issues=issues,
    )


def _resolve(vault: Path, p: Path) -> Path:
    return p if p.is_absolute() else (vault / p).resolve()

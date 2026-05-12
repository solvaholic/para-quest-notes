"""Library entry points for ``pqn-validate``.

Other workflows (and future agents) compose validation by calling these
functions directly, not by shelling out to the CLI. ``pqn-ingest`` calls
:func:`check_basename_available` from its ``propose_filename`` step.
"""

from __future__ import annotations

from pathlib import Path

from .checks import filename_uniqueness
from .contract import Severity, ValidateIssue, ValidateReport
from .pipeline import list_markdown_files, run_pipeline


def validate_vault(
    vault: Path,
    *,
    checks: list[str] | None = None,
    min_severity: Severity = "warning",
    include_archive: bool = False,
) -> ValidateReport:
    """Run the full check suite against ``vault``."""
    return run_pipeline(
        vault,
        paths=None,
        checks=checks,
        min_severity=min_severity,
        include_archive=include_archive,
    )


def validate_paths(
    vault: Path,
    paths: list[Path],
    *,
    checks: list[str] | None = None,
    min_severity: Severity = "warning",
    include_archive: bool = False,
) -> ValidateReport:
    """Run checks but only report issues touching ``paths``.

    Vault-wide context (e.g. the basename index for filename collisions)
    is still built from the entire vault. Focus paths that don't yet
    exist on disk are treated as hypothetical inserts so a planned
    destination can be checked before any file is written.
    """
    return run_pipeline(
        vault,
        paths=paths,
        checks=checks,
        min_severity=min_severity,
        include_archive=include_archive,
    )


def check_basename_available(
    vault: Path,
    basename: str,
    *,
    ignore_path: Path | None = None,
    include_archive: bool = False,
) -> list[ValidateIssue]:
    """Return issues if ``basename`` would collide with an existing note.

    Used by ``pqn-ingest``'s ``propose_filename`` step *before* a
    destination directory is chosen. The hypothetical path is
    ``vault / basename`` (vault root) — we only care about the basename,
    not where it would land, because wikilink ambiguity is basename-only.

    ``ignore_path`` excludes a specific note from collision counting (the
    inbox source about to be renamed shouldn't collide with itself).
    """
    all_md = list_markdown_files(vault, include_archive=include_archive)
    if ignore_path is not None:
        try:
            ignore_resolved = ignore_path.resolve()
        except OSError:
            ignore_resolved = ignore_path
        all_md = [p for p in all_md if p.resolve() != ignore_resolved]

    hypothetical = vault / basename
    return filename_uniqueness.run(vault, [hypothetical], all_md)

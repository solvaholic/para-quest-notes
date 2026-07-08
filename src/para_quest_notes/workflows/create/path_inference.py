"""Path inference for ``pqn-create`` (#45).

Parses a single positional path argument into the components
``pqn-create`` normally requires as explicit flags: ``--vault``,
``--type``, ``--sub-path``, and ``--title``.

Two modes:

1. **Full path** (no ``--type`` given)::

       [<vault>/]<para-type-dir>/<sub-path?>/<filename>.md

   where ``<para-type-dir>`` is one of ``projects``, ``areas``, or
   ``resources``.

2. **Partial path** (``--type`` already given)::

       [<sub-path>/]<filename>[.md]

   The path is interpreted as just the sub-path + title, since the
   PARA type is known from the flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from para_quest_notes.workflows.create.contract import ParaType

# Map directory names to PARA types
_DIR_TO_TYPE: dict[str, ParaType] = {
    "projects": "project",
    "areas": "area",
    "resources": "resource",
}

# Also allow singular forms as a convenience
_DIR_TO_TYPE_SINGULAR: dict[str, ParaType] = {
    "project": "project",
    "area": "area",
    "resource": "resource",
}

# Filename must end with .md (or we append it)
_MD_SUFFIX = ".md"


@dataclass
class InferredInputs:
    """Values inferred from a positional path argument."""

    vault: Path | None = None
    type: ParaType | None = None
    sub_path: str | None = None
    title: str | None = None


class PathInferenceError(Exception):
    """Raised when the path cannot be parsed into valid components."""


def _strip_md(filename: str) -> str:
    """Remove .md suffix if present, return the title."""
    return filename[: -len(_MD_SUFFIX)] if filename.lower().endswith(_MD_SUFFIX) else filename


def infer_from_path(path_str: str, *, has_type: bool = False) -> InferredInputs:
    """Parse a path string into inferred create inputs.

    When ``has_type`` is False (default), the path must contain a PARA
    directory marker to infer the type. When ``has_type`` is True, the
    path is interpreted as ``[sub-path/]<title>[.md]`` - no PARA dir
    needed.

    Raises :class:`PathInferenceError` on ambiguous or invalid paths.
    """
    # Normalize: strip trailing slashes, convert backslashes
    cleaned = path_str.replace("\\", "/").rstrip("/")
    if not cleaned:
        raise PathInferenceError("path is empty")

    # Split into parts
    parts = [p for p in cleaned.split("/") if p]
    if not parts:
        raise PathInferenceError("path is empty after normalization")

    if has_type:
        return _infer_partial(parts, path_str)
    return _infer_full(parts, path_str)


def _infer_partial(parts: list[str], path_str: str) -> InferredInputs:
    """Infer from a partial path when --type is already known.

    Path shape: ``[sub-path/]<title>[.md]``

    If the path happens to start with a PARA dir that matches the
    already-known type, we still consume it correctly (the caller's
    explicit --type overrides). But we don't require it.
    """
    # Check if the first part is a PARA dir - if so, skip it
    # (the user may have typed "projects/sub/Title" with --type project)
    first_lower = parts[0].lower()
    if first_lower in _DIR_TO_TYPE or first_lower in _DIR_TO_TYPE_SINGULAR:
        # Looks like a PARA dir - fall through to full inference
        return _infer_full(parts, path_str)

    # Last part is the filename/title
    filename = parts[-1]
    title = _strip_md(filename)
    if not title.strip():
        raise PathInferenceError(f"path has an empty filename/title: {path_str!r}")

    # Everything before the last part is sub-path
    sub_path: str | None = None
    if len(parts) > 1:
        sub_path = "/".join(parts[:-1])

    return InferredInputs(
        vault=None,
        type=None,  # Caller already has --type
        sub_path=sub_path,
        title=title,
    )


def _infer_full(parts: list[str], path_str: str) -> InferredInputs:
    """Infer from a full path that must contain a PARA directory marker."""
    # Find the PARA directory marker in the path
    para_idx: int | None = None
    para_type: ParaType | None = None
    for i, part in enumerate(parts):
        lower = part.lower()
        if lower in _DIR_TO_TYPE:
            para_idx = i
            para_type = _DIR_TO_TYPE[lower]
            break
        if lower in _DIR_TO_TYPE_SINGULAR:
            para_idx = i
            para_type = _DIR_TO_TYPE_SINGULAR[lower]
            break

    if para_idx is None or para_type is None:
        raise PathInferenceError(
            f"path does not contain a PARA directory "
            f"(projects/, areas/, or resources/): {path_str!r}"
        )

    # Everything before the PARA dir is the vault prefix
    vault_parts = parts[:para_idx]
    # Everything after the PARA dir is sub-path + filename
    after_para = parts[para_idx + 1 :]

    if not after_para:
        raise PathInferenceError(f"path has no filename after the PARA directory: {path_str!r}")

    # Last element is the filename
    filename = after_para[-1]
    # Everything between PARA dir and filename is sub-path
    sub_path_parts = after_para[:-1]

    # Extract title from filename
    title = _strip_md(filename)
    if not title.strip():
        raise PathInferenceError(f"path has an empty filename/title: {path_str!r}")

    # Resolve vault from prefix if non-empty
    vault: Path | None = None
    if vault_parts:
        vault_str = "/".join(vault_parts)
        # Handle absolute paths
        if path_str.startswith("/"):
            vault_str = "/" + vault_str
        vault = Path(vault_str)

    # Build sub-path (may be empty)
    sub_path: str | None = None
    if sub_path_parts:
        sub_path = "/".join(sub_path_parts)

    return InferredInputs(
        vault=vault,
        type=para_type,
        sub_path=sub_path,
        title=title,
    )

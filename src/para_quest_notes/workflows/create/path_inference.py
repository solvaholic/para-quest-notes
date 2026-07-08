"""Path inference for ``pqn-create`` (#45).

Parses a single positional path argument into the components
``pqn-create`` normally requires as explicit flags: ``--vault``,
``--type``, ``--sub-path``, and ``--title``.

A valid path has the shape::

    [<vault>/]<para-type-dir>/<sub-path?>/<filename>.md

where ``<para-type-dir>`` is one of ``projects``, ``areas``, or
``resources`` (the plural PARA directory names used in the vault layout).

The vault is resolved by walking up from the path until the standard
vault markers are found (or via the normal ``--vault`` / env / config
discovery if not embedded in the path).
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


def infer_from_path(path_str: str) -> InferredInputs:
    """Parse a path string into inferred create inputs.

    The path is interpreted as a POSIX-style relative or absolute path.
    We look for a PARA directory name (``projects/``, ``areas/``,
    ``resources/``) as the signal for where the type starts.

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
    title = filename[: -len(_MD_SUFFIX)] if filename.lower().endswith(_MD_SUFFIX) else filename

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

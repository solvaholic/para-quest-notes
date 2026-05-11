"""Built-in checks for ``pqn-validate``.

Each check exposes:

* ``ID``       — stable string id (used in CLI ``--check`` and JSON output).
* ``run(vault, files, all_md)`` — returns ``list[ValidateIssue]``.

The pipeline composes checks; checks do not import each other.
"""

from __future__ import annotations

from . import backmatter_yaml, filename_uniqueness, frontmatter_yaml

ALL_CHECKS = (
    filename_uniqueness,
    frontmatter_yaml,
    backmatter_yaml,
)

CHECKS_BY_ID = {c.ID: c for c in ALL_CHECKS}

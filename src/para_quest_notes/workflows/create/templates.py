"""Backward-compatible template imports for ``pqn-create``.

Template mechanics now live in :mod:`para_quest_notes.workflows.creation`
so missing-note ``pqn-daily`` creation and ``pqn-create`` cannot drift.
"""

from para_quest_notes.workflows.creation import (
    DEFAULT_TEMPLATE_DIR,
    TEMPLATE_VARS,
    TemplateNotFoundError,
    get_template_config,
    load_template,
    render_template,
    resolve_template_path,
)

__all__ = [
    "DEFAULT_TEMPLATE_DIR",
    "TEMPLATE_VARS",
    "TemplateNotFoundError",
    "get_template_config",
    "load_template",
    "render_template",
    "resolve_template_path",
]

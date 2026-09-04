"""Note template loading and deterministic body rendering for ``pqn-create``.

Templates live in the vault at ``<vault>/resources/templates/<name>.md``
(configurable via ``create.template_dir`` in config.yaml). They use a
safe set of body variables: ``$title``, ``$type``, ``$quest_kind``,
``$supports``, ``$source_url``, ``$created``. ``$quest`` is a deprecated
alias for ``$quest_kind`` (kept so pre-#98 templates keep rendering).
Templates may include supplemental frontmatter, interpreted by the compose
step through the shared vault frontmatter helpers. Non-empty stdin bodies use
the same renderer and variable mapping after create inputs are finalized.

Resolution order:
1. Explicit ``--template`` flag (by name or path)
2. Per-type default from config (``create.defaults.<type>``)
3. None (fall through to built-in skeleton)
"""

from __future__ import annotations

import string
from pathlib import Path
from typing import Any

DEFAULT_TEMPLATE_DIR = "resources/templates"

# Safe variables available in templates. ``quest`` is a deprecated alias
# for ``quest_kind`` (kept for pre-#98 templates); see render docstring.
TEMPLATE_VARS = ("title", "type", "quest_kind", "supports", "source_url", "created", "quest")


class TemplateNotFoundError(Exception):
    """Raised when a named template cannot be found."""


def resolve_template_path(
    name_or_path: str,
    *,
    vault: Path,
    template_dir: str = DEFAULT_TEMPLATE_DIR,
) -> Path | None:
    """Resolve a template name or path to an actual file.

    Tries in order:
    1. As a vault-relative path (if it contains a slash or ends with .md)
    2. As a name in the template directory (appends .md if needed)
    """
    # If it looks like a path (has slash or .md suffix), try as-is
    if "/" in name_or_path or name_or_path.endswith(".md"):
        candidate = vault / name_or_path
        if candidate.is_file():
            return candidate

    # Try as a name in the template directory
    name = name_or_path
    if not name.endswith(".md"):
        name = f"{name}.md"
    candidate = vault / template_dir / name
    if candidate.is_file():
        return candidate

    return None


def load_template(
    name_or_path: str,
    *,
    vault: Path,
    template_dir: str = DEFAULT_TEMPLATE_DIR,
) -> str:
    """Load a template file and return its raw content.

    Raises :class:`TemplateNotFoundError` if the template cannot be found.
    """
    path = resolve_template_path(name_or_path, vault=vault, template_dir=template_dir)
    if path is None:
        raise TemplateNotFoundError(
            f"template {name_or_path!r} not found in {template_dir}/ or as a vault-relative path"
        )
    return path.read_text(encoding="utf-8")


def render_template(template_text: str, variables: dict[str, str]) -> str:
    """Render a template with safe variable substitution.

    Uses ``$var`` syntax (Python's string.Template safe_substitute).
    Unknown variables are left as-is rather than raising errors.
    """
    tmpl = string.Template(template_text)
    return tmpl.safe_substitute(variables)


def get_template_config(config_workflows: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Extract template config from the workflows dict.

    Returns (template_dir, defaults) where defaults maps type -> template name.
    """
    create_cfg = config_workflows.get("create") or {}
    template_dir = str(create_cfg.get("template_dir", DEFAULT_TEMPLATE_DIR))
    defaults_raw = create_cfg.get("defaults") or {}
    defaults: dict[str, str] = {}
    for key, val in defaults_raw.items():
        if val is not None:
            defaults[str(key)] = str(val)
    return template_dir, defaults

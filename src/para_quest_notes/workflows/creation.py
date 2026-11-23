"""Shared template-aware note creation primitives.

Workflow policy stays with each caller: destinations, generated metadata,
fallback skeletons, variables, validation, and result contracts. This module
owns the mechanics that must not drift between creation workflows:

* template config, path resolution, and loading;
* whole-note splitting and deterministic body rendering;
* template-or-skeleton body-source selection;
* atomic publication of a new file without replacing a concurrent winner.
"""

from __future__ import annotations

import os
import string
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from para_quest_notes.vault.frontmatter import merge, split_note

DEFAULT_TEMPLATE_DIR = "resources/templates"

# ``quest`` is a deprecated create alias for ``quest_kind``.
TEMPLATE_VARS = ("title", "type", "quest_kind", "supports", "source_url", "created", "quest")


class TemplateNotFoundError(Exception):
    """Raised when a named template cannot be found."""


@dataclass(frozen=True)
class SelectedBody:
    """A rendered body plus any parsed template metadata."""

    body: str
    body_source: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    had_backmatter: bool = False


def resolve_template_path(
    name_or_path: str,
    *,
    vault: Path,
    template_dir: str = DEFAULT_TEMPLATE_DIR,
) -> Path | None:
    """Resolve a template name or vault-relative path."""
    if "/" in name_or_path or name_or_path.endswith(".md"):
        candidate = vault / name_or_path
        if candidate.is_file():
            return candidate

    name = name_or_path if name_or_path.endswith(".md") else f"{name_or_path}.md"
    candidate = vault / template_dir / name
    return candidate if candidate.is_file() else None


def load_template(
    name_or_path: str,
    *,
    vault: Path,
    template_dir: str = DEFAULT_TEMPLATE_DIR,
) -> str:
    """Load one template or raise :class:`TemplateNotFoundError`."""
    path = resolve_template_path(name_or_path, vault=vault, template_dir=template_dir)
    if path is None:
        raise TemplateNotFoundError(
            f"template {name_or_path!r} not found in {template_dir}/ or as a vault-relative path"
        )
    return path.read_text(encoding="utf-8")


def render_template(template_text: str, variables: dict[str, str]) -> str:
    """Render known ``$variables`` while preserving unknown tokens."""
    return string.Template(template_text).safe_substitute(variables)


def select_body(
    *,
    template_name: str | None,
    skeleton: str,
    variables: dict[str, str],
    vault: Path | None,
    template_dir: str = DEFAULT_TEMPLATE_DIR,
) -> SelectedBody:
    """Select and render a whole-note template or the caller's skeleton."""
    if template_name is None:
        return SelectedBody(body=skeleton, body_source="skeleton")
    if vault is None:
        raise RuntimeError("template selection requires a vault")

    try:
        raw = load_template(template_name, vault=vault, template_dir=template_dir)
    except TemplateNotFoundError:
        return SelectedBody(body=skeleton, body_source="skeleton (template not found)")

    split = split_note(raw)
    return SelectedBody(
        body=render_template(split.body, variables),
        body_source=f"template:{template_name}",
        frontmatter=merge(split.backmatter, split.frontmatter),
        had_backmatter=split.had_backmatter,
    )


def get_template_config(config_workflows: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Return ``workflows.create`` template directory and per-type defaults."""
    create_cfg = config_workflows.get("create") or {}
    template_dir = str(create_cfg.get("template_dir", DEFAULT_TEMPLATE_DIR))
    defaults_raw = create_cfg.get("defaults") or {}
    defaults: dict[str, str] = {}
    for key, value in defaults_raw.items():
        if value is not None:
            defaults[str(key)] = str(value)
    return template_dir, defaults


def publish_new_note(destination: Path, content: str) -> None:
    """Atomically publish ``content`` without replacing an existing path.

    A unique sibling temp file is fully written and synced, then hard-linked
    into place. ``FileExistsError`` is preserved so workflow steps can report
    their own collision vocabulary.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = _write_unique_temp(destination, content)
    try:
        os.link(temp, destination)
    finally:
        temp.unlink(missing_ok=True)


def _write_unique_temp(destination: Path, content: str) -> Path:
    while True:
        temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
        except FileExistsError:  # pragma: no cover - UUID collision defense
            continue
        complete = False
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            complete = True
        finally:
            if not complete:
                temp.unlink(missing_ok=True)
        return temp

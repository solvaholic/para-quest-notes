"""Shell completion for the ``pqn-*`` CLIs (#121).

Completion is driven by [argcomplete](https://kislyuk.github.io/argcomplete/)
so the argparse definitions stay the single source of truth: every visible
option name and every ``choices=`` tuple completes for free, with no shell
file duplicating a static list.

This module adds the two things argparse can't infer:

* :func:`enable_completion` — the one-liner each entry point calls right
  before ``parse_args()``.
* the ``complete_*`` functions — vault-derived candidates (Quests,
  sub-paths, templates, daily/archive targets) attached to individual
  arguments via :func:`set_completer`.

**Completion is advisory and read-only.** It never runs a workflow
pipeline, writes a trace, touches the vault, or talks to Ollama. Expected
completion-time failures (no vault resolvable, an optional directory
missing, an unreadable file) yield no dynamic candidates and no terminal
noise — static completion keeps working. Only the expected repository
exception types and filesystem errors are caught, never a bare
``Exception``.
"""

from __future__ import annotations

import argparse
import re
import warnings
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import argcomplete

from para_quest_notes.adapter.config import Config, load_config
from para_quest_notes.adapter.errors import ConfigError, VaultError
from para_quest_notes.adapter.vault import find_vault
from para_quest_notes.vault.quests import discover_quests
from para_quest_notes.workflows.create.templates import (
    get_template_config,
    resolve_template_path,
)

# A completer is anything argcomplete will call. It passes ``prefix``,
# ``action``, ``parser``, and ``parsed_args`` as keyword arguments, so
# every completer here takes ``**kwargs`` and reads only what it needs.
Completer = Callable[..., list[str]]

# PARA type flag value -> the vault top-level directory it files into.
TYPE_DIRS = {
    "project": "projects",
    "area": "areas",
    "resource": "resources",
}

# Errors that are *expected* while completing: the user simply hasn't got
# a vault yet, their config is malformed, or a candidate file went away
# between the glob and the read. Anything else should still blow up loudly
# in a normal run, so it isn't swallowed here.
_EXPECTED_ERRORS = (VaultError, ConfigError, OSError)

# ``pqn-daily`` only ever files date-named notes, so a completion that
# offered every markdown file in inbox/ would be noise.
_DAILY_NOTE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\.md")


def enable_completion(parser: argparse.ArgumentParser) -> None:
    """Wire ``parser`` up for shell completion.

    Call this after every argument is registered and before
    ``parse_args()``. It is a no-op unless the shell invoked the command
    in completion mode (argcomplete keys off ``_ARGCOMPLETE`` in the
    environment), so normal runs are unaffected.
    """
    argcomplete.autocomplete(parser)


def set_completer(action: argparse.Action, completer: Completer) -> argparse.Action:
    """Attach ``completer`` to ``action`` and return the action.

    argcomplete reads a ``completer`` attribute off the action object,
    which ``argparse.Action`` doesn't declare. Isolating the type-ignore
    here keeps every call site clean.
    """
    action.completer = completer  # type: ignore[attr-defined]
    return action


# --------------------------------------------------------------------------- #
# Completion-time context: vault + config, resolved the same way a run would
# --------------------------------------------------------------------------- #


def _load_config(parsed_args: Any) -> Config | None:
    """Load the config a real run would use, honoring a parsed ``--config``."""
    config_arg = getattr(parsed_args, "config", None)
    try:
        return load_config(Path(config_arg) if config_arg else None)
    except _EXPECTED_ERRORS:
        return None


def resolve_context(parsed_args: Any) -> tuple[Path | None, Config | None]:
    """Return ``(vault, config)`` for completion, or ``(None, config)``.

    Uses the same precedence as a normal command — parsed ``--vault``,
    ``PARA_QUEST_VAULT``, cwd discovery, then the config's ``vault:`` —
    by delegating to :func:`find_vault` rather than reimplementing it.
    Returns ``None`` for the vault when nothing resolves, which is a
    perfectly ordinary state mid-completion.
    """
    config = _load_config(parsed_args)
    vault_arg = getattr(parsed_args, "vault", None)
    try:
        return find_vault(arg=vault_arg, config=config), config
    except _EXPECTED_ERRORS:
        return None, config


def _quiet_iterdir(root: Path, pattern: str, *, recursive: bool = True) -> list[Path]:
    """``root.glob``/``rglob`` that returns ``[]`` instead of raising."""
    if not root.is_dir():
        return []
    try:
        matches = root.rglob(pattern) if recursive else root.glob(pattern)
        return sorted(matches)
    except OSError:
        return []


def _stem_or_relpath(vault: Path, paths: Iterable[Path]) -> list[str]:
    """Emit bare stems, falling back to vault-relative paths on collision.

    A bare stem is nicer to type, but only safe when it resolves to
    exactly one file — otherwise selecting it would hand the command an
    ambiguous target it has to reject. Duplicated basenames therefore
    complete as vault-relative paths instead.
    """
    paths = list(paths)
    counts: dict[str, int] = {}
    for p in paths:
        counts[p.stem] = counts.get(p.stem, 0) + 1
    out: list[str] = []
    for p in paths:
        if counts[p.stem] == 1:
            out.append(p.stem)
            continue
        try:
            out.append(p.relative_to(vault).as_posix())
        except ValueError:
            continue
    return sorted(set(out))


# --------------------------------------------------------------------------- #
# Vault-derived completers
# --------------------------------------------------------------------------- #


def complete_quests(*, wikilink: bool = False, **kwargs: Any) -> list[str]:
    """Complete declared Main + Side Quest names from the resolved vault.

    ``wikilink=True`` emits ``[[Name]]`` for arguments that require
    wikilink syntax (``pqn-create --supports``); otherwise bare names,
    which is what ``--quest`` filters accept.
    """
    vault, _ = resolve_context(kwargs.get("parsed_args"))
    if vault is None:
        return []
    try:
        with warnings.catch_warnings():
            # Legacy `quest:` keys warn on read. A completion isn't the
            # place to nag about vault hygiene.
            warnings.simplefilter("ignore")
            quests = discover_quests(vault)
    except _EXPECTED_ERRORS:
        return []
    return [f"[[{q.name}]]" if wikilink else q.name for q in quests]


def complete_quest_wikilinks(**kwargs: Any) -> list[str]:
    """``complete_quests`` in the ``[[Name]]`` form ``--supports`` requires."""
    return complete_quests(wikilink=True, **kwargs)


def complete_sub_paths(**kwargs: Any) -> list[str]:
    """Complete existing directories under the selected PARA top-level.

    Honors a ``--type`` already parsed to the left of the cursor. Without
    one, returns the deduplicated union across ``projects/``, ``areas/``,
    and ``resources/`` — the same three roots ``--type`` chooses between.
    """
    parsed_args = kwargs.get("parsed_args")
    vault, _ = resolve_context(parsed_args)
    if vault is None:
        return []
    note_type = getattr(parsed_args, "type", None)
    tops = [TYPE_DIRS[note_type]] if note_type in TYPE_DIRS else list(TYPE_DIRS.values())

    out: set[str] = set()
    for top in tops:
        base = vault / top
        for child in _quiet_iterdir(base, "*"):
            if not child.is_dir():
                continue
            rel = child.relative_to(base).as_posix()
            if rel:
                out.add(rel)
    return sorted(out)


def complete_templates(**kwargs: Any) -> list[str]:
    """Complete markdown templates under the configured ``create.template_dir``.

    Emits a bare stem when the existing resolver accepts it, and a
    vault-relative path otherwise, so every candidate is a value
    ``--template`` can consume unchanged.
    """
    parsed_args = kwargs.get("parsed_args")
    vault, config = resolve_context(parsed_args)
    if vault is None:
        return []
    template_dir, _defaults = get_template_config(config.workflows if config else {})

    base = vault / template_dir
    out: list[str] = []
    for md in _quiet_iterdir(base, "*.md"):
        if not md.is_file():
            continue
        rel = md.relative_to(base).as_posix()
        stem = rel[: -len(".md")]
        try:
            resolved = resolve_template_path(stem, vault=vault, template_dir=template_dir)
        except OSError:
            continue
        if resolved is not None and resolved.resolve() == md.resolve():
            out.append(stem)
        else:
            out.append(md.relative_to(vault).as_posix())
    return sorted(set(out))


def _daily_candidates(vault: Path) -> list[Path]:
    """``YYYY-MM-DD.md`` notes in the scope ``pqn-daily``'s ResolveTarget searches.

    Vault root (non-recursive), ``inbox/`` (recursive), and
    ``resources/daily_notes/`` (recursive) — kept deliberately in step
    with that step's basename search so a completed value always resolves.
    """
    found: list[Path] = []
    found.extend(_quiet_iterdir(vault, "*.md", recursive=False))
    found.extend(_quiet_iterdir(vault / "inbox", "*.md"))
    found.extend(_quiet_iterdir(vault / "resources" / "daily_notes", "*.md"))

    seen: set[Path] = set()
    unique: list[Path] = []
    for p in found:
        if not _DAILY_NOTE_RE.fullmatch(p.name) or not p.is_file():
            continue
        try:
            key = p.resolve()
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def complete_daily_targets(**kwargs: Any) -> list[str]:
    """Complete ``YYYY-MM-DD`` daily notes from ``pqn-daily``'s search scope."""
    vault, _ = resolve_context(kwargs.get("parsed_args"))
    if vault is None:
        return []
    return _stem_or_relpath(vault, _daily_candidates(vault))


def complete_archive_targets(**kwargs: Any) -> list[str]:
    """Complete Project notes under ``projects/`` — the only archivable scope."""
    vault, _ = resolve_context(kwargs.get("parsed_args"))
    if vault is None:
        return []
    candidates = [
        p
        for p in _quiet_iterdir(vault / "projects", "*.md")
        if p.is_file() and "archive" not in p.relative_to(vault).parts
    ]
    return _stem_or_relpath(vault, candidates)

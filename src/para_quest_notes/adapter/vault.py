"""Vault discovery.

Resolution order (see ``docs/configuration.md``):

1. Explicit ``arg`` (``--vault PATH``)
2. ``PARA_QUEST_VAULT`` environment variable
3. Walk up from ``start_dir`` (default ``cwd``) looking for a marker
4. ``config.vault`` setting
5. Raise ``VaultError`` with a helpful message
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from para_quest_notes.adapter.config import Config
from para_quest_notes.adapter.errors import VaultError

VAULT_ENV_VAR = "PARA_QUEST_VAULT"

# A directory looks like a PARA+Quest vault if it contains both `areas/`
# and `projects/`. Cheap, conventional, and lets us detect a vault without
# requiring a sentinel file the user has to create.
_MARKER_DIRS = ("areas", "projects")


def is_vault(path: Path) -> bool:
    if not path.is_dir():
        return False
    return all((path / m).is_dir() for m in _MARKER_DIRS)


def _walk_up_for_vault(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in (current, *current.parents):
        if is_vault(candidate):
            return candidate
    return None


def find_vault(
    arg: str | os.PathLike[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    start_dir: Path | None = None,
    config: Config | None = None,
) -> Path:
    """Resolve the vault path. See module docstring for order."""
    env = env if env is not None else os.environ

    if arg:
        p = Path(arg).expanduser().resolve()
        if not p.exists():
            raise VaultError(f"vault path does not exist: {p}")
        if not p.is_dir():
            raise VaultError(f"vault path is not a directory: {p}")
        return p

    env_val = env.get(VAULT_ENV_VAR)
    if env_val:
        p = Path(env_val).expanduser().resolve()
        if not p.exists():
            raise VaultError(f"{VAULT_ENV_VAR} points to a nonexistent path: {p}")
        if not p.is_dir():
            raise VaultError(f"{VAULT_ENV_VAR} is not a directory: {p}")
        return p

    start = start_dir if start_dir is not None else Path.cwd()
    found = _walk_up_for_vault(start)
    if found is not None:
        return found

    if config is not None and config.vault is not None:
        p = config.vault.expanduser().resolve()
        if p.is_dir():
            return p
        raise VaultError(f"config.vault is set but not a directory: {p}")

    raise VaultError(
        "could not find a vault. Pass --vault PATH, set "
        f"{VAULT_ENV_VAR}, run from inside a vault (one with 'areas/' "
        "and 'projects/' subdirs), or set 'vault:' in config.yaml."
    )

"""Smoke test: package imports and exposes a version."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import para_quest_notes


def test_version() -> None:
    assert para_quest_notes.__version__


def test_package_declares_typing_support() -> None:
    package_dir = Path(para_quest_notes.__file__).parent
    assert (package_dir / "py.typed").is_file()


def test_smoke_script_ignores_ambient_daily_editor(tmp_path: Path) -> None:
    """The apply smoke must not use a developer's daily-opening config."""
    repo = Path(__file__).resolve().parents[1]
    sentinel = tmp_path / "editor-ran"
    editor = tmp_path / "ambient-editor"
    editor.write_text(f"#!/usr/bin/env bash\ntouch {sentinel}\n", encoding="utf-8")
    editor.chmod(0o755)

    config_home = tmp_path / "ambient-config"
    config_path = config_home / "para-quest-notes" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        f"workflows:\n  daily:\n    open_existing: true\n    editor: ['{editor}']\n",
        encoding="utf-8",
    )
    env = os.environ | {
        "XDG_CONFIG_HOME": str(config_home),
        "PARA_QUEST_VAULT": str(tmp_path / "incorrect-vault"),
    }

    subprocess.run(
        ["bash", "scripts/smoke.sh", "--apply"],
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert not sentinel.exists()

"""Tests for the ``python -m para_quest_notes.corpus`` CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "para_quest_notes.corpus", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_generates_vault(tmp_path: Path) -> None:
    out = tmp_path / "vault"
    res = _run(
        ["--out", str(out), "--seed", "11", "--projects", "3", "--inbox", "2", "--daily", "2"]
    )
    assert res.returncode == 0, res.stderr
    assert "wrote" in res.stdout
    assert out.is_dir()
    assert (out / "_corpus_manifest.json").exists()


def test_cli_refuses_non_empty_without_clean(tmp_path: Path) -> None:
    out = tmp_path / "vault"
    out.mkdir()
    (out / "leftover").write_text("x", encoding="utf-8")
    res = _run(["--out", str(out)])
    assert res.returncode == 2
    assert "not empty" in res.stderr


def test_cli_clean_wipes(tmp_path: Path) -> None:
    out = tmp_path / "vault"
    out.mkdir()
    (out / "leftover").write_text("x", encoding="utf-8")
    res = _run(["--out", str(out), "--clean", "--projects", "1", "--inbox", "0", "--daily", "0"])
    assert res.returncode == 0, res.stderr
    assert not (out / "leftover").exists()


def test_cli_no_manifest_flag(tmp_path: Path) -> None:
    out = tmp_path / "vault"
    res = _run(
        ["--out", str(out), "--no-manifest", "--projects", "1", "--inbox", "0", "--daily", "0"]
    )
    assert res.returncode == 0, res.stderr
    assert not (out / "_corpus_manifest.json").exists()

"""Regenerate the committed ``samples/vault/`` and assert byte-equivalence.

If this test fails, either you intentionally changed the generator
(in which case re-commit ``samples/vault/`` with the same seed) or
nondeterminism crept in (which is a bug).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from para_quest_notes.corpus.generate import GenerateOptions, generate_vault

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_VAULT = REPO_ROOT / "samples" / "vault"

# Must match the seed used to produce the committed vault. If you
# regenerate with different options, update both here and the README.
SAMPLE_OPTIONS = GenerateOptions(
    seed=2026,
    projects=6,
    areas=0,
    resources=0,
    inbox=5,
    daily=7,
    quirk_rate=0.3,
)


def _hash_tree(root: Path) -> dict[str, str]:
    """Map vault-relative POSIX path -> sha256 hex of file contents."""
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.mark.skipif(not SAMPLE_VAULT.exists(), reason="samples/vault not present")
def test_committed_sample_vault_is_reproducible(tmp_path: Path) -> None:
    fresh = tmp_path / "vault"
    generate_vault(fresh, SAMPLE_OPTIONS)
    expected = _hash_tree(SAMPLE_VAULT)
    actual = _hash_tree(fresh)
    if expected != actual:
        only_in_committed = sorted(set(expected) - set(actual))
        only_in_fresh = sorted(set(actual) - set(expected))
        differing = sorted(k for k in expected.keys() & actual.keys() if expected[k] != actual[k])
        pytest.fail(
            "samples/vault drifted from generator output. "
            f"Re-run: uv run python -m para_quest_notes.corpus --out samples/vault "
            f"--seed {SAMPLE_OPTIONS.seed} --clean "
            f"--projects {SAMPLE_OPTIONS.projects} --inbox {SAMPLE_OPTIONS.inbox} "
            f"--daily {SAMPLE_OPTIONS.daily} --quirk-rate {SAMPLE_OPTIONS.quirk_rate}\n"
            f"only in committed: {only_in_committed}\n"
            f"only in fresh:     {only_in_fresh}\n"
            f"differing bytes:   {differing}"
        )

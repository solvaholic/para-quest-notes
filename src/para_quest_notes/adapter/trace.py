"""JSONL run-trace writer.

Default location: ``$XDG_STATE_HOME/para-quest-notes/runs/<ts>.jsonl``,
falling back to ``~/.local/state/para-quest-notes/runs/``.

Each event is a single JSON object on one line. Schema is intentionally
loose - the eval harness in Phase 4 will pin the fields it cares about.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def default_state_dir() -> Path:
    base = os.environ.get("XDG_STATE_HOME")
    base_path = Path(base) if base else Path.home() / ".local" / "state"
    return base_path / "para-quest-notes"


def new_run_path(state_dir: Path | None = None, *, prefix: str = "run") -> Path:
    """Return a fresh ``runs/<ts>.jsonl`` path. Creates the parent dir."""
    base = state_dir if state_dir is not None else default_state_dir()
    runs_dir = base / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return runs_dir / f"{prefix}-{ts}.jsonl"


class TraceWriter:
    """Append-only JSONL writer. Safe to use as a context manager."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a", encoding="utf-8")
        self._opened_at = time.time()

    def write(self, event: dict[str, Any]) -> None:
        record = {"ts": time.time(), **event}
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        if not self._fh.closed:
            self._fh.close()

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.close()

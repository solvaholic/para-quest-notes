"""Markdown report emitter for an eval run.

Produces a single ``report.md`` plus a CSV of per-cell rows. The
report is the human/agent-facing artifact; the CSV is for ad-hoc
analysis.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path

from para_quest_notes.eval.runner import EVALUABLE_STEPS, CellResult, RunSummary


def _bucket(cells: Iterable[CellResult]) -> dict[tuple[str, str], list[CellResult]]:
    out: dict[tuple[str, str], list[CellResult]] = defaultdict(list)
    for c in cells:
        out[(c.model, c.step)].append(c)
    return out


def _accuracy(cells: list[CellResult]) -> tuple[int, int]:
    passes = sum(1 for c in cells if c.verdict.ok)
    return passes, len(cells)


def _responds_rate(cells: list[CellResult]) -> tuple[int, int]:
    rel = [c for c in cells if c.responds is not None]
    passes = sum(1 for c in rel if c.responds and c.responds.ok)
    return passes, len(rel)


def render_markdown(summary: RunSummary) -> str:
    """Build the markdown report string."""
    buf: list[str] = []
    started = datetime.fromtimestamp(summary.started_at, tz=UTC)
    duration = max(0.0, summary.finished_at - summary.started_at)
    buf.append("# Eval report")
    buf.append("")
    buf.append(f"- Run start: `{started.isoformat()}`")
    buf.append(f"- Duration: `{duration:.2f}s`")
    buf.append(f"- Fixtures: `{summary.fixture_count}`")
    buf.append(f"- Models: {', '.join(f'`{m}`' for m in summary.models) or '_none_'}")
    buf.append("")

    bucket = _bucket(summary.cells)
    steps_present = [s for s in EVALUABLE_STEPS if any(s == k[1] for k in bucket)]

    # `responds` baseline (LLM steps only).
    buf.append("## Responds-at-all baseline")
    buf.append("")
    buf.append("Cheap gate: did the model emit parseable JSON for an LLM step?")
    buf.append("")
    if not summary.models:
        buf.append("_No models in run._")
    else:
        buf.append("| Model | Responds rate |")
        buf.append("|---|---|")
        for model in summary.models:
            mc = [c for c in summary.cells if c.model == model]
            p, n = _responds_rate(mc)
            cell = f"{p}/{n} ({_pct(p, n)})" if n else "_n/a_"
            buf.append(f"| `{model}` | {cell} |")
    buf.append("")

    buf.append("## Accuracy by step")
    buf.append("")
    if not steps_present or not summary.models:
        buf.append("_No cells._")
    else:
        header = "| Model | " + " | ".join(steps_present) + " | Overall |"
        sep = "|" + "---|" * (len(steps_present) + 2)
        buf.append(header)
        buf.append(sep)
        for model in summary.models:
            row = [f"`{model}`"]
            total_p = total_n = 0
            for step in steps_present:
                p, n = _accuracy(bucket.get((model, step), []))
                total_p += p
                total_n += n
                row.append(f"{p}/{n} ({_pct(p, n)})" if n else "_n/a_")
            row.append(f"{total_p}/{total_n} ({_pct(total_p, total_n)})" if total_n else "_n/a_")
            buf.append("| " + " | ".join(row) + " |")
    buf.append("")

    # Per-step detail.
    buf.append("## Per-step detail")
    buf.append("")
    for step in steps_present:
        buf.append(f"### {step}")
        buf.append("")
        buf.append("| Fixture | Model | Verdict | Reason |")
        buf.append("|---|---|---|---|")
        rows = sorted(
            (c for c in summary.cells if c.step == step),
            key=lambda c: (c.fixture_id, c.model),
        )
        for c in rows:
            mark = "✅" if c.verdict.ok else "❌"
            reason = c.verdict.reason or ""
            if c.run.escalation:
                reason = f"escalated: {c.run.escalation.get('reason', '')}"
            elif c.run.error:
                reason = f"error: {c.run.error}"
            buf.append(f"| `{c.fixture_id}` | `{c.model}` | {mark} | {_escape(reason)} |")
        buf.append("")

    return "\n".join(buf).rstrip() + "\n"


def render_csv(summary: RunSummary) -> str:
    out = StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "model",
            "temperature",
            "fixture_id",
            "step",
            "verdict_ok",
            "verdict_reason",
            "responds_ok",
            "raw_text",
            "prompt_id",
            "latency_ms",
            "escalation",
            "error",
        ]
    )
    for c in summary.cells:
        writer.writerow(
            [
                c.model,
                c.temperature,
                c.fixture_id,
                c.step,
                int(c.verdict.ok),
                c.verdict.reason,
                "" if c.responds is None else int(c.responds.ok),
                c.run.raw_text or "",
                c.run.prompt_id or "",
                c.run.latency_ms,
                "" if not c.run.escalation else c.run.escalation.get("reason", ""),
                c.run.error or "",
            ]
        )
    return out.getvalue()


def write_report(summary: RunSummary, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / "report.md"
    csv_path = out_dir / "rows.csv"
    md_path.write_text(render_markdown(summary), encoding="utf-8")
    csv_path.write_text(render_csv(summary), encoding="utf-8")
    return md_path


def _pct(num: int, den: int) -> str:
    if den == 0:
        return "0%"
    return f"{(100 * num / den):.0f}%"


def _escape(s: str) -> str:
    # Minimal pipe-escape so the markdown table cell stays valid.
    return s.replace("|", "\\|").replace("\n", " ")


__all__ = [
    "render_csv",
    "render_markdown",
    "write_report",
]

# Synthetic corpus / sample vault

The corpus generator builds a realistic-looking PARA + Quest markdown
vault from generic seeds. It exists for three audiences:

1. **Eval fixtures (Phase 4)** — labeled inputs for the per-step eval
   harness.
2. **Workflow tests** — every workflow can run end-to-end against a
   fresh vault without depending on a real user's notes.
3. **Demos / quickstart** — the committed [`samples/vault/`](../samples/vault/)
   gives someone evaluating the tool a believable sandbox before they
   point a workflow at their real notes.

It is *not* meant to ship in the runtime CLI surface — see PLAN.md
Phase 2 decisions. Invoke via `python -m`:

```bash
uv run python -m para_quest_notes.corpus \
    --out ./demo-vault \
    --seed 2026 \
    --projects 6 --inbox 5 --daily 7 \
    --quirk-rate 0.3
```

## What the generator produces

- Every Main Quest and Side Quest from `seeds.yaml` as a spec-compliant
  Area note under `areas/`.
- A sample of Areas, Projects, and Resources, scattered across the
  vault using realistic location patterns.
- Inbox notes and daily notes.
- A `_corpus_manifest.json` describing every emitted note's
  `(location_kind, frontmatter_kind, quirks)` tags, so eval fixtures
  can index by shape.

The output passes `para_quest_notes.adapter.vault.is_vault()`.

## Note "shape" axes

A note is described by three orthogonal dimensions. The ingest
workflow will reason over the first two; the eval harness will lean on
the third.

### `location_kind` — where the file lives

| Value   | Meaning                                            |
|---------|----------------------------------------------------|
| `para`  | Under `projects/`, `areas/`, or `resources/`       |
| `topic` | Arbitrary topic dir like `Home/`, `Work/`          |
| `quest` | Quest-first dir like `Health/`, `Maintain Home/`   |
| `inbox` | `inbox/`                                           |
| `daily` | `resources/daily_notes/YYYY/MM/`                   |

A real arriving vault will have all five. The product never refers to
historical "gen1/2/3" naming for these; that terminology is specific
to one author and would be meaningless to anyone else.

### `frontmatter_kind` — what's in the YAML block

| Value           | Meaning                                              |
|-----------------|------------------------------------------------------|
| `none`          | No frontmatter                                       |
| `obsidian_only` | `tags`/`aliases`, no PARA or Quest fields            |
| `partial_para`  | Has a `type:` field but no `quest:` / `supports:`    |
| `full`          | Spec-compliant `type` + `quest` + `supports`         |

Inbox notes lean toward `none`/`obsidian_only`. Daily notes are always
bare (the spec exempts them — they inherit Quest context from
contents).

### `quirks` — orthogonal messiness flags

Independently sampled per note at `--quirk-rate`. Some are skipped
when they don't apply (e.g., `missing_supports` requires frontmatter).

| Quirk                | What it produces                                  |
|----------------------|---------------------------------------------------|
| `ambiguous_quest`    | Body mentions multiple Quests                     |
| `has_tasks`          | Adds Obsidian task lines                          |
| `closed_tasks_only`  | All tasks done (archive-eligible signal)          |
| `has_attachments`    | Sibling files in the same directory               |
| `duplicate_title`    | Collides with another note in the corpus          |
| `broken_wikilink`    | Links to a nonexistent note                       |
| `missing_supports`   | Project/Area with tasks but no `supports:` field  |

## Reproducibility

Same `--seed` produces byte-identical output. The
`tests/corpus/test_sample_vault.py` test regenerates
`samples/vault/` and asserts byte-equivalence, so the committed
sandbox can never silently drift from the generator.

If you intentionally change the generator and the test fails, the
failure message contains the exact command to regenerate.

## Programmatic API

```python
from pathlib import Path
from para_quest_notes.corpus import generate_vault, GenerateOptions

result = generate_vault(
    Path("./demo-vault"),
    GenerateOptions(seed=2026, projects=6, inbox=5, daily=7, quirk_rate=0.3),
)
for f in result.files:
    print(f.path, f.frontmatter_kind, sorted(q.value for q in f.quirks))
```

## Why no LLM-generated prose?

Two reasons:

1. **Reproducibility** — the corpus must regenerate identically across
   machines and CI, and Ollama is explicitly excluded from CI.
2. **The ingest workflow keys off structure**, not prose flavor —
   titles, paths, frontmatter, tasks, wikilinks. Faker-class prose is
   enough to exercise it. If Phase 4 eval shows the workflow is
   getting tripped up by Faker-flavored bodies, we can add an
   optional `--llm` augmentation pass later.

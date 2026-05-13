# Eval fixtures

Hand-curated fixtures for the registered eval harness (see
[`docs/PLAN.md`](../../docs/PLAN.md) Phase 4). The loader is
workflow-aware: committed fixtures now cover both `pqn-ingest` and
`pqn-archive`.

Run the harness with:

```bash
# CI-safe: FakeLLM returns each fixture's expected JSON.
uv run python -m para_quest_notes.eval --fake

# Real Ollama against one or more models. Models are run sequentially
# and each is unloaded (keep_alive=0) before the next loads - local
# Ollama is memory-bound and won't tolerate two large models in
# parallel. Hosted inference (HuggingFace, Azure, OpenRouter) could
# parallelize this loop later.
uv run python -m para_quest_notes.eval --models granite4.1:30b,qwen3:30b
```

Reports land under `eval/runs/<timestamp>/` (gitignored).

## Schema

### Ingest fixtures

```yaml
workflow: ingest            # optional today; defaults to ingest
id: my-fixture-id           # required, unique across all files
title: "Train Plan"         # required, the note title the LLM sees
body: |                     # optional, multi-line markdown body
  Want to run a 5K by spring...
frontmatter:                # optional, YAML mapping seeded into ScanResult
  type: project
quest_catalog:              # required if pick_quest is expected
  - { name: Health,  kind: main }
  - { name: Connect, kind: main }
expected:
  classify_para:
    type: project           # one of project | area | resource
  pick_quest:
    acceptable:
      - [Health]
      - [Health, Connect]
    # OR, for resources where the workflow short-circuits:
    # skipped: true
  propose_filename:
    canonical: "train plan" # canonical form: lowercase, alnum-only,
                             # single-spaced; matches judges.canonical_filename
  plan_destination:
    destination: "projects/Train Plan.md"  # vault-relative posix
```

### Archive fixtures

```yaml
workflow: archive
id: archive-5k-completed
title: "Train for 5K"
body: |
  # Train for 5K
  ...
completed_tasks:
  - "- [x] Finished week 8 without skipping a session"
inbound_links:
  - basename: Health
    snippet: "[[Train for 5K]] turned into a steady habit."
fake_response: |
  Finished the training block and made running feel routine again....
expected:
  generate_outcome:
    keywords:
      - running habit
      - 30-minute runs
      - sustainable baseline
```

You don't have to declare every step's expectation. The runner only
judges steps you provide an `expected.<step>` for.

## Conventions

- **One concept per fixture id.** Keep `id` short and descriptive
  (`ambiguous-quest-running`, not `fixture7`).
- **Use real-feeling titles and bodies.** Faker garble is what the
  synthetic corpus already gives us; eval fixtures should look like
  notes a human would actually triage.
- **Document why a fixture is interesting.** A `# comment:` line at the
  top of the YAML is enough.
- **Keep the catalog small.** 2-4 quests per fixture is plenty. Bigger
  catalogs make the runner slower without adding signal.
- **Keep legacy ingest fixtures unchanged unless needed.** Omitting
  `workflow:` still means `ingest`.

## Status

Phase 4 lands with ~7 starter fixtures. Plan target is ~30 before Phase
4 is "done" - grow the set as eval signal demands.

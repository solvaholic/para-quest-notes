# Eval fixtures

Hand-curated fixtures for the per-step `pqn-ingest` eval harness
(see [`docs/PLAN.md`](../../docs/PLAN.md) Phase 4). Each YAML file
holds either one fixture (a mapping with `id`) or a list of them.

Run the harness with:

```bash
# CI-safe: FakeLLM returns each fixture's expected JSON.
uv run python -m para_quest_notes.eval --fake

# Real Ollama against one or more models. Models are run sequentially
# and each is unloaded (keep_alive=0) before the next loads — local
# Ollama is memory-bound and won't tolerate two large models in
# parallel. Hosted inference (HuggingFace, Azure, OpenRouter) could
# parallelize this loop later.
uv run python -m para_quest_notes.eval --models granite4.1:30b,qwen3:30b
```

Reports land under `eval/runs/<timestamp>/` (gitignored).

## Schema

```yaml
id: my-fixture-id          # required, unique across all files
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
    # any-of: pick passes if it equals any acceptable set exactly
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

You don't have to declare every step's expectation. The runner only
judges steps you provide an `expected.<step>` for.

## Conventions

- **One concept per fixture id.** Keep `id` short and descriptive
  (`ambiguous-quest-running`, not `fixture7`).
- **Use real-feeling titles and bodies.** Faker garble is what the
  synthetic corpus already gives us; eval fixtures should look like
  notes a human would actually triage.
- **Document why a fixture is interesting.** A `# comment:` line at
  the top of the YAML is enough.
- **Keep the catalog small.** 2-4 quests per fixture is plenty.
  Bigger catalogs make the runner slower without adding signal.

## Status

Phase 4 lands with ~7 starter fixtures. Plan target is ~30 before
Phase 4 is "done" — grow the set as eval signal demands.

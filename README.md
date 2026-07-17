# para-quest-notes

Local, scripted workflows for managing markdown notes organized by
**PARA + Quest**, powered by small LLMs running locally via
[Ollama](https://ollama.com/).

> **Status:** v0.4 shipped. CLI surface and JSON contracts are
> stable. See the [releases page](https://github.com/solvaholic/para-quest-notes/releases)
> for what's new.

## Why

Most "AI for notes" tools require sending your notes to someone else's
servers. This one doesn't. Workflows do as much as possible with plain
Python, and only call a local LLM for the bits that genuinely need
natural-language judgment (classification, summarization, escalation
when rules don't fit).

The PARA + Quest organization model (see
[`docs/notes-system.md`](docs/notes-system.md)) is the value
proposition: it lets you align day-to-day work with long-term goals.
The workflows preserve that reasoning, locally.

## Design principles

1. **Local first.** No cloud LLM calls. Notes never leave your machine.
2. **Scripts are the brains.** LLMs only do what scripts can't: judgment
   calls and natural-language summarization.
3. **Small models welcome.** Targeted at models that fit on a laptop
   (Granite 4, Gemma 3, Qwen 3, Phi-4 reasoning, etc.).
4. **CLI first, agent-friendly.** Every workflow is a CLI you can pipe
   and cron. Structured JSON output is a first-class citizen, so an
   agent can wrap a workflow without ever seeing your note bodies.
5. **Bring your own vault.** Install once with `pipx`/`uv tool install`,
   then run against any vault on disk.

## Status / roadmap

- [x] Phase 0: repo bootstrap
- [x] Phase 1: thin runtime adapter (Ollama client, Step/Workflow,
      escalation, config + vault discovery)
- [x] Phase 2: synthetic corpus generator (also serves as demo vault —
      see [`docs/corpus.md`](docs/corpus.md) and
      [`samples/vault/`](samples/vault/))
- [x] Phase 3: pilot workflow - `pqn-ingest` (inbox → PARA + Quest)
      — see [`docs/workflows/ingest.md`](docs/workflows/ingest.md)
- [x] Phase 4: per-step eval harness landed (matrix over models /
      prompts). See [`docs/eval.md`](docs/eval.md). Fixture growth
      toward ~30 promoted to Phase 7.
- [x] Phase 5: remaining workflows
  - [x] Slice 1: shared `vault/` + `adapter/cli.py` + `pqn-validate`
        (see [`docs/workflows/validate.md`](docs/workflows/validate.md))
  - [x] Slice 2: `pqn-create` (no-LLM)
  - [x] Slice 3: `pqn-archive` (Projects only, no-LLM)
  - [x] Slice 4: `pqn-daily` (filing-only, no LLM)
- [x] Phase 5.5: LLM polish + contributor onboarding
      (`pqn-create` inbox fallback, `pqn-archive --generate-outcome`,
      [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md))
- [x] Phase 6: polish + v0.1 release (see
      [`docs/RELEASING.md`](docs/RELEASING.md))
- [x] `pqn-quests` — generated Quest index (read-only, no LLM;
      v0.5.x). See [`docs/workflows/quests.md`](docs/workflows/quests.md).
      Lands the shared `vault/links.py` + `vault/scope.py` building
      blocks.
- [x] `pqn-tasks` — read-only reporter for scheduled/due tasks
      (v0.5; see [`docs/workflows/tasks.md`](docs/workflows/tasks.md))
- [ ] Phase 7: grow eval fixtures toward ~30; revisit
      `generate_outcome` judge
- [ ] Phase 8 (deferred): agent SKILL.md wrappers

## Quickstart: end-to-end against the sample vault

A small (~30-note) sample vault lives at
[`samples/vault/`](samples/vault/). The walkthrough below exercises
A small (~30-note) sample vault lives at
[`samples/vault/`](samples/vault/). The walkthrough below exercises
the seven core workflow `pqn-*` CLIs against a throwaway copy of it, so
you can see the whole toolchain on first read without risking real
notes. (The read-only `pqn-tasks` reporter isn't shown here — the
sample vault carries no due-dated tasks — but see
[`docs/workflows/tasks.md`](docs/workflows/tasks.md).)

You'll need [Ollama](https://ollama.com) running locally for the
LLM-using steps (`pqn-ingest`, the final `pqn-archive` step). The
documented default model is `granite4.1:30b` (~18 GB); override
with `--model` if you have something smaller. For a "what to use
when" answer, see
[`docs/eval.md` → Model recommendations](docs/eval.md#model-recommendations),
driven by a real eval run.

```bash
# 0. Set up the repo and make a throwaway vault
git clone https://github.com/solvaholic/para-quest-notes.git
cd para-quest-notes
uv sync --dev
cp -R samples/vault /tmp/demo-vault
```

### 1. `pqn-validate` — confirm the vault is well-shaped (no LLM)

Read-only audit: duplicate basenames, malformed front/backmatter.

```bash
uv run pqn-validate --vault /tmp/demo-vault
```

A clean sample vault reports `no issues found.` Full options:
[`docs/workflows/validate.md`](docs/workflows/validate.md).

### 2. `pqn-ingest` — triage notes from `inbox/` into PARA + Quest (LLM)

```bash
# Dry-run: see proposed moves, touch nothing
uv run pqn-ingest --vault /tmp/demo-vault

# Inspect one file, JSON output for piping to jq
uv run pqn-ingest --vault /tmp/demo-vault \
    --file inbox/Possible\ trial\ smile.md --format json | jq

# When you trust the model, --apply does the moves
uv run pqn-ingest --vault /tmp/demo-vault --apply
```

`pqn-ingest` **rewrites incoming wikilinks** across the vault when
it renames a note (skipping `archive/`), so keep `--apply` off
until you trust a given model on a given vault. Sample-vault inbox
notes are Faker-generated nonsense; the LLM will often escalate,
which is fine for adapter testing, less great for "look how clever
this is." Hand-write a few plausible inbox notes for a real demo.
Full JSON contract and escalation shape:
[`docs/workflows/ingest.md`](docs/workflows/ingest.md).

### 3. `pqn-create` — create a single new note in its PARA + Quest home (no LLM)

```bash
uv run pqn-create --vault /tmp/demo-vault \
    --type project --title "Tidy The Garage" \
    --quest side --supports '[[Maintain Home]]' --apply
```

Files a new Project at `projects/Tidy The Garage.md` with
frontmatter pre-populated. Drop `--apply` for dry-run. Omit
`--supports` and `pqn-create` tries to infer the Quest from the
destination path; on miss it files to `inbox/`. Full options:
[`docs/workflows/create.md`](docs/workflows/create.md).

### 4. `pqn-daily` — file a daily note into `resources/daily_notes/` (no LLM)

`pqn-daily` is filing-only; you (or another tool) author the note,
`pqn-daily` puts it in the right place.

```bash
# Author a daily note at the vault root
echo "# 2026-05-16" > /tmp/demo-vault/2026-05-16.md

# File it (dry-run, then --apply)
uv run pqn-daily --vault /tmp/demo-vault 2026-05-16
uv run pqn-daily --vault /tmp/demo-vault 2026-05-16 --apply
```

Basename search covers vault root, `inbox/`, and
`resources/daily_notes/`. Full options:
[`docs/workflows/daily.md`](docs/workflows/daily.md).

### 5. `pqn-archive --generate-outcome` — archive a Project, LLM writes the Outcome (LLM)

Closes out the Project created in step 3. `--cancel-open-tasks`
rewrites the template's open task to cancelled; `--generate-outcome`
hands the LLM the note body and asks for an `## Outcome` paragraph.

```bash
# Dry-run is cheap and model-free: it tells you what would happen
# but does not call the LLM
uv run pqn-archive --vault /tmp/demo-vault "Tidy The Garage" \
    --cancel-open-tasks --generate-outcome

# --apply calls the model, appends ## Outcome on success, then
# moves the file to archive/
uv run pqn-archive --vault /tmp/demo-vault "Tidy The Garage" \
    --cancel-open-tasks --generate-outcome --apply
```

Empty or `INSUFFICIENT_CONTEXT` responses escalate and abort the
write (no `## Outcome` is appended, no move happens). Full options:
[`docs/workflows/archive.md`](docs/workflows/archive.md).

### 6. `pqn-config` — inspect the effective config with provenance (no LLM)

Read-only: reports the config a `pqn-*` run will actually use, and where
each value came from (default / `config.yaml` / env / flag).

```bash
# Full effective config, or one section at a time
uv run pqn-config --vault /tmp/demo-vault
uv run pqn-config --vault /tmp/demo-vault --section models --format json | jq
```

It also surfaces drift: any per-workflow `workflows.<name>.model` override
is reported with `honored: false`, because no workflow reads it yet. Full
options: [`docs/workflows/config.md`](docs/workflows/config.md).

### 7. `pqn-quests` — generate the Quest index (no LLM)

Read-only: walks the vault, groups Areas/Projects by the Quest(s) they
support (and Resources by incoming links), and prints the rollup. It
never owns an index note — redirect the markdown wherever you want.

```bash
# Markdown index to stdout (redirect into a note)
uv run pqn-quests --vault /tmp/demo-vault
uv run pqn-quests --vault /tmp/demo-vault > /tmp/demo-vault/index.md

# Flat JSON, or scoped to one Quest / PARA type
uv run pqn-quests --vault /tmp/demo-vault --format json | jq
uv run pqn-quests --vault /tmp/demo-vault --quest '[[Health]]'
```

Full options: [`docs/workflows/quests.md`](docs/workflows/quests.md).

### What just happened

Each run wrote a JSONL trace under
`~/.local/state/para-quest-notes/runs/`; the path is printed in
text output. Read it to see exactly which prompt produced which
decision.

### Trying it on your own notes

The workflows key off vault structure: any directory with both
`areas/` and `projects/` at its root counts as a vault. Vault
discovery resolves in this order: `--vault PATH` →
`PARA_QUEST_VAULT` env var → walking up from `cwd` → `vault:` in
`~/.config/para-quest-notes/config.yaml`. See
[`docs/configuration.md`](docs/configuration.md) for the full
discovery rules and config-file shape.

### Running from cron or an agent

Every CLI accepts `--format json`, shares a uniform exit-code
contract, and writes a JSONL trace you can consume after the fact.
See [`docs/headless.md`](docs/headless.md) for crontab examples,
exit codes, and a "what not to cron" callout. For the intended
command ordering and dependency map across the CLIs, see
[`docs/workflows/command-sequence.md`](docs/workflows/command-sequence.md).

### Generating a fresh sample vault

```bash
uv run python -m para_quest_notes.corpus \
    --out ./demo-vault --seed 42 --projects 8 --inbox 6 --daily 14
```

See [`docs/corpus.md`](docs/corpus.md) for the full shape taxonomy.

## Install

Install the released CLIs straight from this repo's git tag:

```bash
uv tool install git+https://github.com/solvaholic/para-quest-notes@v0.4.1
# or
pipx install git+https://github.com/solvaholic/para-quest-notes@v0.4.1
```

Either command installs all `pqn-*` commands onto your `PATH`
(the eight workflow CLIs plus the `pqn-eval` harness).
PyPI publishing is deferred to a later release; track the
[releases page](https://github.com/solvaholic/para-quest-notes/releases)
for new tags.

### From a clone (for development)

```bash
git clone https://github.com/solvaholic/para-quest-notes.git
cd para-quest-notes
uv sync --dev
uv run pytest
```

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for the dev
loop, branch flow, and how to add an eval fixture.

## License

MIT. See [LICENSE](LICENSE).

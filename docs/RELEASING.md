# Releasing para-quest-notes

This is the checklist for cutting a release. Follow it top to
bottom; skipping steps is how we end up with a tag that doesn't
install, or release notes that reference docs that aren't on the
tagged commit.

Releases are git tags on this repo (`vX.Y.Z`). PyPI publishing is
deferred; users install with
`uv tool install git+https://github.com/solvaholic/para-quest-notes@vX.Y.Z`.

## Pre-flight

- [ ] Working tree is clean on `main`, all PRs for this release
      merged, `git pull --ff-only` is a no-op.
- [ ] `README.md`, `docs/PLAN.md`, and any per-workflow docs in
      `docs/workflows/` reflect what's actually shipping. The
      Quickstart commands must work as written.
- [ ] `README.md` Install section references the tag you're about
      to cut (not a stale older tag). Status banner reflects current
      state.
- [ ] All internal links in `README.md` resolve (one-liner:
      `grep -oE '\]\([^)]+\)' README.md | sed 's/](\(.*\))/\1/'
      | grep -v '^http' | while read l; do [ -e "${l%%#*}" ] ||
      echo MISS $l; done`).
- [ ] `pyproject.toml` `version` reflects the version you're
      about to tag.
- [ ] `pyproject.toml` `Development Status` classifier still
      matches reality (3-Alpha through v0.x; bump to 4-Beta when
      we have a real second user driving fixes, 5-Production
      when the API is stable).

## Verify the dev build

The repo's standard verify suite must be green. **No Ollama in
CI**, but local-only `pqn-eval` runs against real models are part
of the "should I tag this?" judgment for releases that change
prompts or LLM-using steps.

```sh
uv sync
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
uv run pqn-eval --fake          # smoke test the harness
```

For releases that touch prompts, fixtures, or any LLM-using step,
also run a real-model eval and skim the report. See
[`docs/eval.md`](eval.md) for the command.

## Smoke test the install

Unit tests cover the workflows in isolation but cannot catch
packaging bugs (missing files in the wheel, broken entry points,
import-time errors that pytest masks via fixtures). Always do
this before tagging.

```sh
# 1. Build sdist + wheel from a clean tree.
uv build

# 2. Install the wheel into an isolated tool environment.
uv tool install --force ./dist/para_quest_notes-*.whl

# 3. Confirm every entry point is on PATH and --help works.
for cli in pqn-validate pqn-ingest pqn-create pqn-daily \
           pqn-archive pqn-eval; do
  command -v "$cli" >/dev/null && "$cli" --help >/dev/null \
    && echo "OK $cli" || echo "FAIL $cli"
done

# 4. Round-trip the README Quickstart against a fresh copy of
#    samples/vault. Every command must exit 0.
cp -R samples/vault /tmp/release-smoke
uv tool run --from para-quest-notes pqn-validate \
    --vault /tmp/release-smoke
# ... walk the rest of the Quickstart ...
rm -rf /tmp/release-smoke

# 5. Clean up the test install and build artifacts.
uv tool uninstall para-quest-notes
rm -rf dist/
```

If anything in the wheel-install smoke fails, fix in a follow-up
PR before tagging. A failing smoke means real users get the same
failure on the documented install command.

## Cut the release

Pick the right SemVer bump:

- **Patch** (`v0.1.1`) — bug fixes, doc corrections, no CLI
  surface changes, no JSON schema changes.
- **Minor** (`v0.2.0`) — new workflows, new CLI flags, new
  optional JSON fields, prompt revisions that change eval scores.
- **Major** (`v1.0.0`) — breaking CLI changes, breaking JSON
  schema changes, vault-on-disk layout changes. Don't tag a
  major bump without a deprecation cycle in the prior minor.

```sh
# 1. Bump version in pyproject.toml, commit on a branch, open a
#    PR titled "Release vX.Y.Z" that updates pyproject.toml plus
#    any README/PLAN checkboxes that change at release time.
#    Merge that PR before continuing. PRs rebase-and-merge (no
#    merge commit) - see docs/CONTRIBUTING.md "Branch flow".

# 2. From the tip of main (the release PR's commit), tag and push.
git checkout main && git pull --ff-only
VERSION=$(grep '^version' pyproject.toml | cut -d'"' -f2)
git tag -a "v${VERSION}" -m "Release v${VERSION}"
git push origin "v${VERSION}"

# 3. Draft the GitHub Release. --generate-notes pulls merged PR
#    titles since the last tag; edit the result to lead with
#    user-facing highlights.
gh release create "v${VERSION}" --generate-notes \
    --title "v${VERSION}" --draft
```

Open the draft in the browser and:

- [ ] Lead with one paragraph of user-facing highlights (what
      can users do now that they couldn't on the previous tag?).
- [ ] Call out any breaking changes prominently. None expected
      during v0.x without prior deprecation.
- [ ] Spot-check the auto-generated commit/PR list for accuracy.
- [ ] Verify the install command in the release notes references
      the right tag.
- [ ] Publish.

After publish, verify the install command from the release notes
actually works against a clean machine or container:

```sh
uv tool install --force \
    git+https://github.com/solvaholic/para-quest-notes@vX.Y.Z
pqn-validate --help
uv tool uninstall para-quest-notes
```

## Post-release

- [ ] Update `docs/PLAN.md` to tick boxes that closed at this
      release; move follow-ups to the next phase.

The issue-to-release mapping is already covered without extra
bookkeeping: each closed issue's timeline shows the PR that closed
it ("closed via PR #N"), and that PR is listed in the release's
auto-generated notes. If you ever need to group fixed issues by
shipped version for users, reach for a GitHub **Milestone per
release** (it tracks issues and PRs together and surfaces on each
one automatically) rather than per-issue labels.

## Lessons learned

Seed entries from real releases here; future-you will thank you.

- **v0.1.0** — first tag. This checklist was authored during the
  v0.1.0 cut itself, adapted from
  `solvaholic/markdown-loom/docs/RELEASING.md`. The pre-flight,
  verify, and smoke-install steps were all run by hand against
  v0.1.0 (see the Phase 6 PRs #11-#15 for the audit trail), so
  the checklist captures what we actually did, not aspirations.
  Refine it on v0.1.1 / v0.2.0 with whatever this dry-run missed.
- **v0.2.0** — first minor bump. The SemVer call was clear from
  this doc's own rule ("prompt revisions that change eval scores"
  = minor): two prompt revisions plus a new `pqn-validate` check
  put it past patch. Real-model eval (5 models) was green at
  100% responds-at-all, so the prompt changes didn't break
  generation. We also dropped the post-release `fixed-in-vX.Y`
  labeling step: it was added when this checklist was first
  authored (v0.1.0) without a recorded use, nothing in the repo
  ever consumed the labels, and the issue-to-release mapping is
  already there in each issue's "closed via PR #N" timeline plus
  the auto-generated release notes. Lesson: don't carry a
  bookkeeping step without a consumer. Use a Milestone if you
  ever need to group fixed issues by version.

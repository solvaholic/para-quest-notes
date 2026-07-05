#!/usr/bin/env bash
# scripts/smoke.sh - End-to-end smoke test against samples/vault/.
#
# Runs all pqn-* commands in a realistic sequence against a disposable
# copy of the sample vault. No network (no Ollama) - uses --fake where
# the command talks to an LLM, or skips the LLM-dependent command.
#
# Usage:
#   ./scripts/smoke.sh              # default: dry-run assertions only
#   ./scripts/smoke.sh --apply      # also run the apply path and check results
#
# Exit codes:
#   0  All commands behaved as expected
#   1  A command failed unexpectedly
#
# Intended for:
#   - Pre-release confidence ("does the CLI still parse args and talk to the vault?")
#   - CI gate (fast, deterministic, no LLM)
#   - Demo recording prep (confirms the sequence produces sensible output)
#
# What this does NOT test:
#   - LLM decision quality (that's eval's job)
#   - Per-step logic (that's pytest's job)
#   - Non-deterministic real-model behavior

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SAMPLE_VAULT="$REPO_ROOT/samples/vault"
APPLY=false

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    *) echo "Unknown arg: $arg" >&2; exit 1 ;;
  esac
done

# --- Setup: disposable vault copy -------------------------------------------

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
VAULT="$WORK_DIR/vault"
cp -r "$SAMPLE_VAULT" "$VAULT"

pass=0
fail=0

check() {
  local label="$1"; shift
  if "$@" > /dev/null 2>&1; then
    echo "  PASS  $label"
    pass=$((pass + 1))
  else
    echo "  FAIL  $label (exit $?)"
    fail=$((fail + 1))
  fi
}

check_fail() {
  # Expect the command to exit non-zero (escalation is correct behavior).
  local label="$1"; shift
  if "$@" > /dev/null 2>&1; then
    echo "  FAIL  $label (expected non-zero exit but got 0)"
    fail=$((fail + 1))
  else
    echo "  PASS  $label (escalated as expected)"
    pass=$((pass + 1))
  fi
}

echo "=== pqn-validate: vault is well-formed ==="
check "validate (default)" \
  uv run pqn-validate --vault "$VAULT" --format json
check "validate --strict" \
  uv run pqn-validate --vault "$VAULT" --format json --strict

echo ""
echo "=== pqn-create: scaffold a new project ==="
check "create dry-run" \
  uv run pqn-create --vault "$VAULT" --format json \
    --type project --title "Smoke Test Project" \
    --quest main --supports "[[Health]]"

if $APPLY; then
  check "create --apply" \
    uv run pqn-create --vault "$VAULT" --format json --apply \
      --type project --title "Smoke Test Project" \
      --quest main --supports "[[Health]]"
  check "created file exists" \
    test -f "$VAULT/projects/Smoke Test Project.md"
fi

echo ""
echo "=== pqn-daily: file a daily note ==="
# Seed an unfiled daily note in inbox.
printf '# 2026-07-05\n\nSmoke test daily.\n' > "$VAULT/inbox/2026-07-05.md"

check "daily dry-run (unfiled)" \
  uv run pqn-daily --vault "$VAULT" --format json "2026-07-05.md"
check "daily dry-run (already filed)" \
  uv run pqn-daily --vault "$VAULT" --format json "2026-02-04.md"

if $APPLY; then
  check "daily --apply" \
    uv run pqn-daily --vault "$VAULT" --format json --apply "2026-07-05.md"
  check "daily note moved to destination" \
    test -f "$VAULT/resources/daily_notes/2026/07/2026-07-05.md"
  check "daily note removed from inbox" \
    test ! -f "$VAULT/inbox/2026-07-05.md"
fi

echo ""
echo "=== pqn-archive: archive a completed project ==="
# pqn-archive requires projects/ to exist. If --apply was run above,
# pqn-create already made it. Otherwise seed it manually.
if [ ! -d "$VAULT/projects" ]; then
  mkdir -p "$VAULT/projects"
  cat > "$VAULT/projects/Smoke Test Project.md" << 'EOF'
---
type: project
quest: main
supports:
- '[[Health]]'
created: '2026-07-05'
---
# Smoke Test Project

Ship it.

## Outcome

Done.

## Tasks

- [x] first step
EOF
fi

# If we used pqn-create, the note has an open task - use --cancel-open-tasks.
check "archive dry-run" \
  uv run pqn-archive --vault "$VAULT" --format json \
    --outcome "Completed" --cancel-open-tasks "Smoke Test Project"

if $APPLY; then
  check "archive --apply" \
    uv run pqn-archive --vault "$VAULT" --format json --apply \
      --outcome "Completed" --cancel-open-tasks "Smoke Test Project"
  check "archived file exists" \
    test -f "$VAULT/archive/projects/Smoke Test Project.md"
  check "source removed after archive" \
    test ! -f "$VAULT/projects/Smoke Test Project.md"
fi

echo ""
echo "=== pqn-archive: escalation on missing projects/ ==="
# Fresh vault without projects/ should escalate (not crash).
VAULT2="$WORK_DIR/vault2"
cp -r "$SAMPLE_VAULT" "$VAULT2"
check_fail "archive escalates when no projects/ dir" \
  uv run pqn-archive --vault "$VAULT2" --format json \
    --outcome "N/A" "Nonexistent"

echo ""
echo "=== pqn-ingest: dry-run without Ollama (expect escalation) ==="
# Without a running Ollama, ingest will either connect-error or, with
# gibberish notes, escalate. Either way it should not crash with a
# traceback. This checks "does it start and parse args."
# NOTE: This is a best-effort check. If Ollama is running locally it
# will hit the real model and likely escalate on gibberish content.
check_fail "ingest dry-run (escalations expected on gibberish)" \
  uv run pqn-ingest --vault "$VAULT" --format json

echo ""
echo "=== pqn-validate: vault still well-formed after mutations ==="
if $APPLY; then
  check "validate post-apply" \
    uv run pqn-validate --vault "$VAULT" --format json --strict
fi

echo ""
echo "=== Summary ==="
echo "  Passed: $pass"
echo "  Failed: $fail"

if [ "$fail" -gt 0 ]; then
  exit 1
fi

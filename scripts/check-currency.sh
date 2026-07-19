#!/usr/bin/env bash
# scripts/check-currency.sh - Coarse currency check (no LLM, no network).
#
# Guards against the most common drift caught by manual currency sweeps:
# a pqn-* command ships but isn't wired into every surface that's supposed
# to know about it. This is the mechanical half of that sweep - it does not
# judge whether docs *describe* a command correctly, only whether each
# command is present in each surface.
#
# Source of truth: the [project.scripts] table in pyproject.toml. New
# commands auto-enroll the moment their entry point lands.
#
# Surfaces checked, per command:
#   - scripts/smoke.sh        (command is invoked in the smoke sequence)
#   - docs/workflows/<name>.md OR docs/<name>.md   (has a doc)
#   - README.md               (mentioned)
#   - AGENTS.md               (mentioned)
#
# Usage:
#   ./scripts/check-currency.sh
#
# Exit codes:
#   0  Every command is covered on every surface it's expected on
#   1  At least one gap (a command exists but is missing from a surface)
#
# What this does NOT do:
#   - Judge doc quality or freshness (that's a human/LLM review job)
#   - Check individual flags (deferred; brittle to automate)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

SMOKE="scripts/smoke.sh"
README="README.md"
AGENTS="AGENTS.md"

# --- Exemptions --------------------------------------------------------------
# Commands legitimately absent from a given surface. Keep this list short and
# justify every entry, so exemptions stay auditable instead of silent.
#
#   pqn-eval: the eval *harness*, not a vault workflow. It doesn't act on a
#             vault, so it has no place in the sample-vault smoke sequence or
#             in AGENTS.md's workflow orientation. It is documented in
#             docs/eval.md and listed in README.md.
SMOKE_EXEMPT="pqn-eval"
AGENTS_EXEMPT="pqn-eval"

in_list() {
  # in_list <needle> <space-separated-haystack>
  local needle="$1" hay="$2" item
  for item in $hay; do
    [ "$item" = "$needle" ] && return 0
  done
  return 1
}

mentions() {
  # mentions <command> <file> - word-boundary match so pqn-create can't
  # satisfy a hypothetical pqn-created, and vice versa.
  local ep="$1" file="$2"
  [ -f "$file" ] || return 1
  grep -qE "(^|[^a-z0-9-])${ep}([^a-z0-9-]|$)" "$file"
}

# --- Enumerate entry points from [project.scripts] ---------------------------
entry_points="$(
  awk '
    /^\[project\.scripts\]/ { in_section = 1; next }
    /^\[/                   { in_section = 0 }
    in_section              { print }
  ' pyproject.toml | grep -oE '^pqn-[a-z0-9-]+' | sort -u
)"

if [ -z "$entry_points" ]; then
  echo "check-currency: no pqn-* entry points found in [project.scripts]" >&2
  echo "                (did pyproject.toml move or change shape?)" >&2
  exit 1
fi

# --- Check each surface ------------------------------------------------------
fail=0
printf "  %-14s %-8s %-8s %-8s %-8s\n" "COMMAND" "smoke" "docs" "README" "AGENTS"
printf "  %-14s %-8s %-8s %-8s %-8s\n" "-------" "-----" "----" "------" "------"

for ep in $entry_points; do
  name="${ep#pqn-}"

  # smoke.sh
  if in_list "$ep" "$SMOKE_EXEMPT"; then
    s="exempt"
  elif mentions "$ep" "$SMOKE"; then
    s="ok"
  else
    s="NO"; fail=$((fail + 1))
    echo "  MISSING: $ep not invoked in $SMOKE" >&2
  fi

  # docs: docs/workflows/<name>.md or docs/<name>.md
  if [ -f "docs/workflows/${name}.md" ] || [ -f "docs/${name}.md" ]; then
    d="ok"
  else
    d="NO"; fail=$((fail + 1))
    echo "  MISSING: $ep has no docs/workflows/${name}.md or docs/${name}.md" >&2
  fi

  # README.md
  if mentions "$ep" "$README"; then
    r="ok"
  else
    r="NO"; fail=$((fail + 1))
    echo "  MISSING: $ep not mentioned in $README" >&2
  fi

  # AGENTS.md
  if in_list "$ep" "$AGENTS_EXEMPT"; then
    a="exempt"
  elif mentions "$ep" "$AGENTS"; then
    a="ok"
  else
    a="NO"; fail=$((fail + 1))
    echo "  MISSING: $ep not mentioned in $AGENTS" >&2
  fi

  printf "  %-14s %-8s %-8s %-8s %-8s\n" "$ep" "$s" "$d" "$r" "$a"
done

echo ""
if [ "$fail" -gt 0 ]; then
  echo "check-currency: FAIL ($fail gap(s)). See MISSING lines above." >&2
  echo "Add the command to the surface it's missing from, or - if it's a" >&2
  echo "genuine exception - add it to the exemption list in this script" >&2
  echo "with a one-line justification." >&2
  exit 1
fi

echo "check-currency: OK - every command is covered on every expected surface."

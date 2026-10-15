#!/usr/bin/env bash
# 🔒 litmus: muckrake must stay project-agnostic.
#
# Fails (exit 1) if src/, tests/ or pyproject.toml mention
# django | popolo | wagtail | undertheinfluence | openlobbying | uti
# (case-insensitive, whole words), other than the whitelisted hits below, or if
# any of those names is a dependency in pyproject.toml or a package in uv.lock.
#
# Usage: scripts/litmus.sh [path-to-muckrake]   (default: this checkout)
set -uo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT" || { echo "no such dir: $ROOT"; exit 2; }

PATTERN='\b(django|popolo|wagtail|undertheinfluence|openlobbying|uti)\b'

# Whitelist: extended regexes matched against "file:line:text" grep output.
# Each names the GitHub organisation or a provenance, not a consumer project's
# behaviour, so none stops a new project using muckrake.
WHITELIST=(
  # The HTTP User-Agent points at muckrake's own repo, which lives in the
  # `openlobbying` GitHub org. It identifies muckrake, not a consumer.
  '^src/muckrake/extract/fetch\.py:[0-9]+:.*github\.com/openlobbying/muckrake'
  # Test comment citing the upstream bug report behind a fixture. No behaviour.
  '^tests/test_dates\.py:[0-9]+:.*openlobbying/openlobbying#[0-9]+'
)

fail=0

hits=$(grep -rnIiE "$PATTERN" src tests pyproject.toml --exclude-dir=__pycache__ 2>/dev/null || true)
violations=""
whitelisted=""
while IFS= read -r line; do
  [ -z "$line" ] && continue
  ok=0
  for w in "${WHITELIST[@]}"; do
    if printf '%s\n' "$line" | grep -qE "$w"; then ok=1; break; fi
  done
  if [ $ok -eq 1 ]; then whitelisted+="$line"$'\n'; else violations+="$line"$'\n'; fi
done <<< "$hits"

# Dependency check: [project] dependencies / dependency-groups and the lockfile.
dep_hits=$(sed -n '/^dependencies = \[/,/^\]/p;/^\[dependency-groups\]/,/^\[/p' pyproject.toml \
  | grep -iE '"(django|djangorestframework|wagtail|popolo|undertheinfluence|openlobbying)[^"]*"' || true)
lock_hits=$(grep -iE '^name = "(django|djangorestframework|wagtail|popolo|undertheinfluence|openlobbying)' uv.lock 2>/dev/null || true)

echo "== 🔒 muckrake litmus ($ROOT)"
if [ -n "$whitelisted" ]; then
  echo "-- whitelisted hits:"
  printf '%s' "$whitelisted" | sed 's/^/   ok  /'
fi
if [ -n "$violations" ]; then
  echo "-- VIOLATIONS (source/tests/pyproject):"
  printf '%s' "$violations" | sed 's/^/   FAIL /'
  fail=1
fi
if [ -n "$dep_hits" ]; then
  echo "-- VIOLATIONS (pyproject dependencies):"; printf '%s\n' "$dep_hits" | sed 's/^/   FAIL /'; fail=1
fi
if [ -n "$lock_hits" ]; then
  echo "-- VIOLATIONS (uv.lock packages):"; printf '%s\n' "$lock_hits" | sed 's/^/   FAIL /'; fail=1
fi

if [ $fail -eq 0 ]; then echo "PASS"; else echo "FAIL"; fi
exit $fail

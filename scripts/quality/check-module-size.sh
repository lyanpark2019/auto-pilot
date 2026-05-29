#!/usr/bin/env bash
# Enforce the ≤500-line module rule with documented exceptions.
# Scope: tracked *.py / *.sh (excl docs/) + every SKILL.md.
# Exceptions live in module_size_budget.txt as <path>|<max_lines>.
# bash 3.2-safe (no associative arrays) so it runs on the macOS host too.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

LIMIT=500
BUDGET="scripts/quality/module_size_budget.txt"
fail=0

cap_for() {
  [ -f "$BUDGET" ] || { echo "$LIMIT"; return; }
  awk -F'|' -v p="$1" '$1==p {print $2; found=1} END{if(!found) print ""}' "$BUDGET" \
    | grep -E '^[0-9]+$' || echo "$LIMIT"
}

while IFS= read -r f; do
  [ -f "$f" ] || continue
  n=$(wc -l < "$f" | tr -d ' ')
  limit=$(cap_for "$f")
  if [ "$n" -gt "$limit" ]; then
    echo "BLOCKED: $f is $n lines (limit $limit). Split it, or register an exception in $BUDGET with a reason." >&2
    fail=1
  fi
done < <(git ls-files '*.py' '*.sh' '*/SKILL.md' 'SKILL.md' | grep -vE '^docs/' | sort -u)

[ "$fail" -eq 0 ] && echo "module-size: OK (limit $LIMIT, exceptions in $BUDGET)"
exit "$fail"

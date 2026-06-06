#!/usr/bin/env bash
# ⓓ-5 ruff-import-integrity.sh — PostToolUse Bash
# After ruff format / ruff check --fix: verify changed .py files compile + have no
# F821/F401 import errors.
# PostToolUse cannot deny — emits systemMessage warning listing violating files.
# Bounded: checks max 20 files.
# Unparseable stdin → allow (fail-open).
# Non-git directory → allow (fail-open).
set -uo pipefail

payload=$(cat)

cmd=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("command") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

[[ -z "$cmd" ]] && exit 0

# Only fire when command ran ruff format or ruff check --fix
is_ruff_op=0
if printf '%s' "$cmd" | grep -qE 'ruff[[:space:]]+format'; then
  is_ruff_op=1
fi
if printf '%s' "$cmd" | grep -qE 'ruff[[:space:]]+(check[[:space:]]+)?--fix'; then
  is_ruff_op=1
fi

[[ "$is_ruff_op" == "0" ]] && exit 0

# Determine working directory
work_dir=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("cwd") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")
[[ -z "$work_dir" ]] && work_dir="$(pwd)"

# Determine ruff executable: prefer repo .venv, then python3 -m ruff, else skip
ruff_bin=""
if [[ -x "$work_dir/.venv/bin/ruff" ]]; then
  ruff_bin="$work_dir/.venv/bin/ruff"
elif [[ -x "$work_dir/.venv/bin/python3" ]]; then
  if "$work_dir/.venv/bin/python3" -m ruff --version &>/dev/null 2>&1; then
    ruff_bin="$work_dir/.venv/bin/python3 -m ruff"
  fi
elif python3 -m ruff --version &>/dev/null 2>&1; then
  ruff_bin="python3 -m ruff"
fi

[[ -z "$ruff_bin" ]] && exit 0  # ruff not available — skip silently

# Get changed .py files — fail-open if not a git repo
changed_files=$(git -C "$work_dir" diff --name-only -- '*.py' 2>/dev/null || true)
changed_files_head=$(git -C "$work_dir" diff --name-only HEAD -- '*.py' 2>/dev/null || true)
all_changed=$(printf '%s\n%s' "$changed_files" "$changed_files_head" | sort -u 2>/dev/null | grep -v '^$' | head -20 || true)

[[ -z "$all_changed" ]] && exit 0

violations=()

while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  abs_f="$work_dir/$f"
  [[ ! -f "$abs_f" ]] && continue

  # py_compile check
  if ! python3 -m py_compile "$abs_f" 2>/dev/null; then
    violations+=("$f (syntax error)")
    continue
  fi

  # ruff F821,F401 check
  ruff_out=""
  if [[ "$ruff_bin" == *" "* ]]; then
    # has space → use eval
    ruff_out=$(eval "$ruff_bin check --select F821,F401 --no-fix --quiet '$abs_f'" 2>/dev/null || true)
  else
    ruff_out=$("$ruff_bin" check --select F821,F401 --no-fix --quiet "$abs_f" 2>/dev/null || true)
  fi

  if [[ -n "$ruff_out" ]]; then
    violations+=("$f (F821/F401: $ruff_out)")
  fi
done <<< "$all_changed"

if [[ "${#violations[@]}" -gt 0 ]]; then
  msg="ruff-import-integrity: import violations detected after ruff run — review:"
  for v in "${violations[@]}"; do
    msg="$msg  $v;"
  done
  printf '{"systemMessage":"%s"}' "${msg//\"/\\\"}"
fi

exit 0

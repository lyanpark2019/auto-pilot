#!/usr/bin/env bash
# ⓓ-2 branch-lock.sh — PreToolUse Bash
# Deny `git commit` / `git push` when the operation targets main or master.
#   commit  → gate on current HEAD branch
#   push    → gate on push REFSPEC DST (not HEAD); bare push/no-refspec → HEAD
# Bypass: AUTO_PILOT_MAIN_OK=1.
# Worktree-aware: uses the tool_input.cwd field when available.
# Unparseable stdin → allow (fail-open).
set -euo pipefail

deny() {
  local reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "${reason//\"/\\\"}"
  exit 0
}

payload=$(cat)

cmd=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("command") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

# Unparseable → allow
if [[ -z "$cmd" ]] && ! printf '%s' "$payload" | python3 -c 'import sys,json; json.load(sys.stdin)' 2>/dev/null; then
  printf '[hook:branch-lock] fail-open: unparseable stdin\n' >&2
  exit 0
fi

[[ -z "$cmd" ]] && exit 0

# Only fire when command actually contains a commit or push (word boundary check).
# Tolerate git GLOBAL options before the subcommand (`git -C <path> commit`,
# `git -c k=v push`, `git --no-pager push`) — review r1: adjacency-only regex
# let those bypass the lock.
GIT_OPTS='([[:space:]]+(-C[[:space:]]+[^[:space:];|&]+|-c[[:space:]]+[^[:space:];|&]+|--[A-Za-z0-9-]+(=[^[:space:];|&]*)?))*'

# STRATEGY SHIFT (r4): collect EVERY `git <global-opts> commit|push` invocation
# and deny if ANY targets a protected branch — order-independent.
segs=$(printf '%s' "$cmd" | grep -oE "(^|[[:space:];|&])git${GIT_OPTS}[[:space:]]+(commit|push)([[:space:]]|\$)" || echo "")

[[ -z "$segs" ]] && exit 0

# Bypass — hook env OR an explicit env-prefix on the command itself (the hook
# process inherits the SESSION env, so a tool-call prefix never reaches the
# check above; accept the literal token as operator intent — r3 fix, same
# class as deletion-diff-guard).
if [[ "${AUTO_PILOT_MAIN_OK:-0}" == "1" ]]; then
  exit 0
fi
if printf '%s' "$cmd" | grep -q 'AUTO_PILOT_MAIN_OK=1'; then
  exit 0
fi

# Determine working directory: use tool_input.cwd if present, else CWD
work_dir=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("cwd") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")

if [[ -z "$work_dir" ]]; then
  work_dir="$(pwd)"
fi

# Parse every git commit/push invocation out of the full command string.
# For each invocation emit one line:
#   commit <c_path_or_NONE>
#   push   <c_path_or_NONE> <dst_refspec_or___CURRENT__>
# Then bash consumes those lines to decide deny/allow.
#
# r5 change: push gates on DST refspec, not HEAD branch — fixes false-deny
# when HEAD=main but pushing a feature branch.
# Residual (documented): multiple -C compose in git; we honour the last only.
invocations=$(printf '%s' "$cmd" | python3 -c '
import sys, re

cmd = sys.stdin.read()

# Split the command on shell compound separators (; && || | newline)
# to find individual simple-command tokens.
# We process the whole string as a token list instead of splitting by
# separator, because separators can appear inside quoted strings; a
# best-effort split is good enough for a bash hook.
segments = re.split(r";|&&|\|\||[\n(]", cmd)

for seg in segments:
    tokens = seg.split()
    if not tokens:
        continue
    # Skip env-var assignments at the front (VAR=val)
    start = 0
    while start < len(tokens) and re.match(r"^[A-Z_][A-Z_0-9]*=", tokens[start]):
        start += 1
    if start >= len(tokens):
        continue
    # Must start with "git"
    if tokens[start] != "git":
        continue

    # Collect global options (flags and their arguments), then find subcommand
    i = start + 1
    c_path = None
    while i < len(tokens):
        t = tokens[i]
        if t == "-C" and i + 1 < len(tokens):
            c_path = tokens[i + 1]
            i += 2
        elif t.startswith("-c") and not t.startswith("--"):
            # -c key=val (may be one or two tokens)
            if t == "-c":
                i += 2  # skip the value token
            else:
                i += 1
        elif t.startswith("--"):
            i += 1
        elif t.startswith("-"):
            i += 1
        else:
            break  # found the subcommand

    if i >= len(tokens):
        continue
    subcmd = tokens[i]
    rest = tokens[i + 1:]  # everything after the subcommand

    c_str = c_path if c_path is not None else "NONE"

    if subcmd == "commit":
        print(f"commit {c_str}")
    elif subcmd == "push":
        # Drop flags to find remote + refspec
        non_flags = [t for t in rest if not t.startswith("-")]
        if len(non_flags) <= 1:
            # bare push or push <remote> only — dst = current HEAD
            print(f"push {c_str} __CURRENT__")
        else:
            refspec = non_flags[1]
            dst = refspec.split(":", 1)[1] if ":" in refspec else refspec
            print(f"push {c_str} {dst}")
' 2>/dev/null || echo "")

[[ -z "$invocations" ]] && exit 0

while IFS= read -r inv; do
  [[ -z "$inv" ]] && continue

  # Parse: "commit <c_path>" or "push <c_path> <dst>"
  subcmd=$(printf '%s' "$inv" | cut -d' ' -f1)
  c_path=$(printf '%s' "$inv" | cut -d' ' -f2)
  dst=$(printf '%s' "$inv" | cut -d' ' -f3)

  # Resolve the -C target directory
  target="$work_dir"
  if [[ "$c_path" != "NONE" && -n "$c_path" ]]; then
    if [[ "$c_path" == /* ]]; then
      target="$c_path"
    else
      target="$work_dir/$c_path"
    fi
  fi

  if [[ "$subcmd" == "push" ]]; then
    if [[ "$dst" == "__CURRENT__" ]]; then
      branch=$(git -C "$target" branch --show-current 2>/dev/null || echo "")
    else
      branch="$dst"
    fi
  else
    # commit: gate on current HEAD
    branch=$(git -C "$target" branch --show-current 2>/dev/null || echo "")
  fi

  if [[ "$branch" == "main" || "$branch" == "master" ]]; then
    deny "Refusing git commit/push on protected branch '$branch' (target: $target). Set AUTO_PILOT_MAIN_OK=1 to override."
  fi
done <<< "$invocations"

exit 0

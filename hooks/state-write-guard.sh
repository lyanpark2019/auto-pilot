#!/usr/bin/env bash
# state-write-guard.sh — PreToolUse Edit|Write|MultiEdit|Bash
#
# Enforces two invariants from CLAUDE.md rules-for-this-plugin:
#   1. state.json writes must go through _state.save_state (not direct Edit/Write)
#   2. $ROOT mutations via git am/apply/format-patch must go through
#      WorktreeManager.apply_to_main, not direct Bash invocation.
#
# Detection: active only under AUTO_PILOT_SUBAGENT_ROLE=worker|codex-reviewer|claude-reviewer|review-gatekeeper|tech-critic-lead|escalation-resolver
# (mirrors pre-reviewer-write.sh env-gate pattern).  Unset or unknown role → exit 0.
# Bypass envs: AUTO_PILOT_ALLOW_STATE_WRITE=1 (Edit/Write), AUTO_PILOT_ALLOW_MAIN_MUTATE=1 (Bash).
# Fail-closed on parse error (unparseable JSON or missing tool_name → exit 2).
# Fail-open on any other internal error (guard errors → exit 0, logged to stderr).
set -uo pipefail

role="${AUTO_PILOT_SUBAGENT_ROLE:-}"
case "$role" in
  worker|codex-reviewer|claude-reviewer|review-gatekeeper|tech-critic-lead|escalation-resolver) ;;
  *) exit 0 ;;
esac

input=$(cat)

tool_name=$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("__PARSE_FAIL__")
    sys.exit(0)
val = d.get("tool_name", "")
if not isinstance(val, str) or not val:
    print("__PARSE_FAIL__")
    sys.exit(0)
print(val)
')

if [ "$tool_name" = "__PARSE_FAIL__" ] || [ -z "$tool_name" ]; then
  echo "auto-pilot: BLOCKED state-write-guard — unparseable or missing tool_name (fail-closed)" >&2
  exit 2
fi

case "$tool_name" in
  Edit|Write|MultiEdit)
    if [ "${AUTO_PILOT_ALLOW_STATE_WRITE:-}" = "1" ]; then
      exit 0
    fi

    file_path=$(printf '%s' "$input" | python3 -c '
import json, os, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("__PARSE_FAIL__")
    sys.exit(0)
ti = d.get("tool_input")
if not isinstance(ti, dict):
    print("__PARSE_FAIL__")
    sys.exit(0)
raw = ti.get("file_path", "")
# Normalize path to collapse ../ traversal before pattern matching.
# This closes the path-traversal bypass:
#   /repo/.planning/auto-pilot/../auto-pilot/state.json
# normalizes to:
#   /repo/.planning/auto-pilot/state.json  ← caught by the guard below
print(os.path.normpath(raw) if raw else "")
')

    if [ "$file_path" = "__PARSE_FAIL__" ]; then
      echo "auto-pilot: BLOCKED state-write-guard $tool_name — unparseable or non-dict tool_input (fail-closed)" >&2
      exit 2
    fi

    # Only the canonical loop-state file path is guarded (rel + any-abs-prefix).
    # A broad */state.json glob would false-deny unrelated fixtures.
    case "$file_path" in
      */.planning/auto-pilot/state.json|.planning/auto-pilot/state.json)
        echo "auto-pilot: BLOCKED Edit/Write to state.json ($file_path) — writes must go through _state.save_state (set AUTO_PILOT_ALLOW_STATE_WRITE=1 to override)" >&2
        exit 2
        ;;
      *) exit 0 ;;
    esac
    ;;

  Bash)
    # Bypasses honored ONLY from the real process/session env, NOT a command-string
    # prefix: a tool-call prefix never reaches this hook's env and accepting the
    # literal token would make the guard self-grantable by any subagent (SEC5 class).
    # Two invariants, two bypasses: AUTO_PILOT_ALLOW_MAIN_MUTATE for git apply-to-main,
    # AUTO_PILOT_ALLOW_STATE_WRITE for the state.json shell-write guard. The verdict
    # below is computed first, then each block-type honors its own bypass.

    # Extract command string — fail-closed on parse failures.
    # shellcheck disable=SC2016 # python heredoc — $ and backtick are regex literals
    verdict=$(printf '%s' "$input" | python3 -c '
import json, os, re, shlex, sys

try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("BLOCK:unparseable JSON")
    sys.exit(0)

ti = d.get("tool_input")
if not isinstance(ti, dict):
    print("BLOCK:non-dict tool_input")
    sys.exit(0)

cmd_val = ti.get("command", "")
if not isinstance(cmd_val, str):
    print("BLOCK:non-string command")
    sys.exit(0)

cmd = cmd_val

# --- 1. Eval-construct detection (mirrors branch-lock.sh strategy) ---
# Fail CLOSED on command-substitution $(...)/$VAR/${VAR}, backtick, eval,
# sh/bash/zsh -c.  Any of these in the command string is treated as a
# potential apply_to_main bypass — static analysis cannot resolve it.
# \x27 = single-quote; avoids bash string-nesting issues in this Python block.
_eval_construct = re.search(r"\$[\w({\x27\"]|`|\beval\b|\b(?:ba|z)?sh\s+-c\b", cmd)
if _eval_construct:
    print("BLOCK:eval-construct")
    sys.exit(0)

# --- 2. Normalize separators and tokenize ---
# Strip subshell / brace-group / compound-separator metacharacters so a
# wrapped invocation tokenizes the same as a bare one (mirrors branch-lock.sh).
sanitized = re.sub(r"[(){}]", " ", cmd)
sanitized = re.sub(r"&&|\|\||[;&|\n]", " ", sanitized)

try:
    tokens = shlex.split(sanitized)
except ValueError:
    # Unbalanced quotes — fail closed.
    print("BLOCK:shlex-unbalanced-quotes")
    sys.exit(0)


# --- 3. Guard shell writes to state.json (redirect / tee / dd / cp / mv) ---
# The Edit/Write branch denies direct edits to state.json; a worker could
# otherwise clobber it via a Bash shell write. Resolve each candidate target
# and block when it normalizes to .planning/auto-pilot/state.json.
STATE_SUFFIX = os.path.join(".planning", "auto-pilot", "state.json")

# FIX 1 (awk sub-case): scan the RAW command string for redirects embedded inside
# quoted program strings (e.g. awk BEGIN-redirect-state.json). shlex.split
# collapses {}-sanitized awk programs into one token so the token-level redirect
# scanner below misses them. A regex scan on the raw string catches these before
# tokenization and is conservative: any > token followed (with optional whitespace
# and optional quote) by a path containing the STATE_SUFFIX pattern is blocked.
_raw_redirect_re = re.compile(
    r">+\s*[\x22\x27]{0,1}(?P<p>[^\x22\x27>\s]*\.planning[/]auto-pilot[/]state\.json)"
)
for _m in _raw_redirect_re.finditer(cmd):
    _candidate = _m.group("p").strip("\x22\x27")
    if os.path.normpath(_candidate).endswith(os.sep + STATE_SUFFIX) or \
            os.path.normpath(_candidate) == STATE_SUFFIX:
        print("BLOCK:shell-write-to-state:" + _candidate)
        sys.exit(0)


def _is_state(path):
    if not path:
        return False
    norm = os.path.normpath(path)
    return norm == STATE_SUFFIX or norm.endswith(os.sep + STATE_SUFFIX)


redirect_targets = []
for k, tok in enumerate(tokens):
    # FIX 2: allow optional leading fd number (e.g. 1>, 2>>, 1>|) before the
    # redirect operator so `echo bad 1> state.json` is caught like `echo bad > state.json`.
    if re.match(r"^[0-9]*>>?$", tok) and k + 1 < len(tokens):
        redirect_targets.append(tokens[k + 1])
    else:
        # Attached redirect: [fd]>file or [fd]>>file (no space between op and path)
        m = re.match(r"^[0-9]*>>?(?P<f>[^>&].*)$", tok)
        if m:
            redirect_targets.append(m.group("f"))

# tee / dd of=... / cp / mv write their target argument. dd uses of=PATH;
# tee/cp/mv take positional path args (cp/mv final arg is the destination).
# FIX 1: also catch sed -i, perl -i/-pi, install, ln -sf, rm, ed, ex which
# modify or replace state.json in-place without a shell redirect operator.
final_arg_cmds = {"cp", "mv"}
inplace_cmds = {"sed", "perl"}
last_arg_cmds = {"install", "ed", "ex"}
for k, tok in enumerate(tokens):
    basename = os.path.basename(tok)
    if basename == "tee":
        for arg in tokens[k + 1:]:
            if not arg.startswith("-"):
                redirect_targets.append(arg)
    elif basename == "dd":
        for arg in tokens[k + 1:]:
            if arg.startswith("of="):
                redirect_targets.append(arg[len("of="):])
    elif basename in final_arg_cmds:
        positionals = [a for a in tokens[k + 1:] if not a.startswith("-")]
        if positionals:
            redirect_targets.append(positionals[-1])
    elif basename in inplace_cmds:
        # sed -i and perl -i / perl -pi edit files in-place; treat every non-flag
        # argument as a potential target when an in-place flag is present.
        # sed -i '' / sed -i.bak consume the next token as the backup suffix on BSD
        # but the flag is still present — check for the flag, then collect file args.
        rest = tokens[k + 1:]
        has_inplace = any(
            re.match(r"^-[^-]*i", a) or a in ("-i", "-pi") for a in rest
        )
        if has_inplace:
            for arg in rest:
                if not arg.startswith("-"):
                    redirect_targets.append(arg)
    elif basename == "ln":
        # ln -sf <src> <dst> replaces dst via symlink; treat the last positional as target.
        rest = tokens[k + 1:]
        flags = [a for a in rest if a.startswith("-")]
        has_sf = any("f" in f or "s" in f for f in flags)
        if has_sf:
            positionals = [a for a in rest if not a.startswith("-")]
            if positionals:
                redirect_targets.append(positionals[-1])
    elif basename == "rm":
        # rm state.json defeats the invariant (file gone = lock lost).
        for arg in tokens[k + 1:]:
            if not arg.startswith("-"):
                redirect_targets.append(arg)
    elif basename in last_arg_cmds:
        # install <src> <dst> and ed/ex <file> — last non-flag arg is the target.
        positionals = [a for a in tokens[k + 1:] if not a.startswith("-")]
        if positionals:
            redirect_targets.append(positionals[-1])

for target in redirect_targets:
    if _is_state(target):
        print("BLOCK:shell-write-to-state:" + target)
        sys.exit(0)

# --- 4. Guard git am/apply/format-patch ---
# These verbs apply patches directly to the working tree, bypassing
# WorktreeManager.apply_to_main.  git allows intermediate value-taking flags
# (-C <path>, -c <name=value>) before the subcommand; we skip those pairs
# correctly so `git -C /repo am x.mbox` is still caught.
GUARDED_VERBS = {"am", "apply", "format-patch"}
GIT_VALUE_FLAGS = {"-C", "-c"}

for i, tok in enumerate(tokens):
    basename = os.path.basename(tok)
    if basename != "git":
        continue
    j = i + 1
    while j < len(tokens):
        t = tokens[j]
        if t in GIT_VALUE_FLAGS:
            j += 2  # skip flag AND its value token
        elif t.startswith("-"):
            j += 1  # other flags (no value token)
        else:
            break   # found the subcommand
    if j < len(tokens) and tokens[j] in GUARDED_VERBS:
        print("BLOCK:git-apply-verb:" + tokens[j])
        sys.exit(0)

print("ALLOW")
')

    case "$verdict" in
      ALLOW) ;;
      BLOCK:shell-write-to-state:*)
        if [ "${AUTO_PILOT_ALLOW_STATE_WRITE:-}" = "1" ]; then
          exit 0
        fi
        echo "auto-pilot: BLOCKED Bash shell-write to state.json — writes must go through _state.save_state (set AUTO_PILOT_ALLOW_STATE_WRITE=1 to override): ${verdict#BLOCK:shell-write-to-state:}" >&2
        exit 2
        ;;
      BLOCK:*)
        if [ "${AUTO_PILOT_ALLOW_MAIN_MUTATE:-}" = "1" ]; then
          exit 0
        fi
        echo "auto-pilot: BLOCKED Bash \$ROOT-mutating git verb — must go through WorktreeManager.apply_to_main (set AUTO_PILOT_ALLOW_MAIN_MUTATE=1 to override): ${verdict#BLOCK:}" >&2
        exit 2
        ;;
      *)
        # Unexpected verdict — fail closed.
        echo "auto-pilot: BLOCKED state-write-guard Bash — unexpected verdict: $verdict (fail-closed)" >&2
        exit 2
        ;;
    esac
    ;;
esac

exit 0

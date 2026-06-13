#!/usr/bin/env bash
# auto-pilot reviewer sandbox: blocks reviewer agents from writing outside
# their CONTRACT_DIR/outputs/<role>/ scope or running mutation commands.
#
# Detection: PM sets AUTO_PILOT_SUBAGENT_ROLE in the spawned subagent env.
# When unset, hook is a no-op for non-reviewer dispatches (worker, etc.).
set -uo pipefail

role="${AUTO_PILOT_SUBAGENT_ROLE:-}"
case "$role" in
  codex-reviewer|claude-reviewer|review-gatekeeper|tech-critic-lead) ;;
  *) exit 0 ;;
esac

input=$(cat)
allowed_output_dir="${AUTO_PILOT_OUTPUT_DIR:-}"
if [ -z "$allowed_output_dir" ]; then
  echo "auto-pilot: AUTO_PILOT_OUTPUT_DIR unset for reviewer role $role" >&2
  exit 2
fi

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
  echo "auto-pilot: BLOCKED reviewer ($role) — unparseable or missing tool_name (fail-closed)" >&2
  exit 2
fi

case "$tool_name" in
  Edit|Write|MultiEdit)
    file_path=$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    print("__PARSE_FAIL__")
    sys.exit(0)
ti = d.get("tool_input")
if not isinstance(ti, dict):
    print("__PARSE_FAIL__")
    sys.exit(0)
print(ti.get("file_path", ""))
')
    if [ "$file_path" = "__PARSE_FAIL__" ]; then
      echo "auto-pilot: BLOCKED reviewer ($role) $tool_name — unparseable or non-dict tool_input (fail-closed)" >&2
      exit 2
    fi
    case "$file_path" in
      "$allowed_output_dir"/*) exit 0 ;;
      *)
        echo "auto-pilot: BLOCKED reviewer ($role) $tool_name to $file_path (allowed: $allowed_output_dir/)" >&2
        exit 2 ;;
    esac
    ;;
  Bash)
    # Extract command string — fail-closed on parse failures (non-dict or
    # non-string tool_input would str()-render to a form no pattern catches).
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
# sh/bash/zsh -c.  A reviewer command string containing any of these is
# treated as a mutation attempt: we cannot statically resolve what executes.
# ANSI-C ($\x27) and locale ($") quoting also caught.
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

# --- 3. Token-based mutation check ---

# Dangerous standalone binaries (path-qualified or bare).
BLOCKED_BINS = {
    "rm","mv","chmod","chown","tee","curl","wget","ssh","scp",
    "rsync","cp","ln","dd","install","truncate",
}

# git subcommands that mutate the working tree or remote.
GIT_MUTATION_VERBS = {
    "commit","push","reset","checkout","stash","am",
    "rebase","merge","worktree","restore","clean",
}

# in-place editor flags for sed/awk/perl/ruby/php.
INPLACE_RE = re.compile(
    r"^(sed|awk)$",
)
INPLACE_FLAG_RE = re.compile(r"^-[^-]*i")  # -i / -i.bak / -in-place

# python -c exact flag (not -mpy_c or -c as a prefix of another flag).
PYTHON_RE = re.compile(r"^python[\d.]*$")

i = 0
while i < len(tokens):
    tok = tokens[i]
    basename = os.path.basename(tok)

    # Dangerous binary check (bare or path-qualified).
    if basename in BLOCKED_BINS:
        print("BLOCK:dangerous-binary:" + basename)
        sys.exit(0)

    # git mutation: walk past global flags (including value-taking -C <path>,
    # -c <name=value>, --git-dir, etc.) to find the subcommand.
    # Value-taking short opts: -C and -c each consume the next token as their value.
    if basename == "git":
        GIT_VALUE_FLAGS = {"-C", "-c"}
        j = i + 1
        while j < len(tokens):
            t = tokens[j]
            if t in GIT_VALUE_FLAGS:
                j += 2  # skip flag AND its value token
            elif t.startswith("-"):
                j += 1  # other flags (no value token)
            else:
                break   # found the subcommand
        if j < len(tokens) and tokens[j] in GIT_MUTATION_VERBS:
            print("BLOCK:git-mutation:" + tokens[j])
            sys.exit(0)
        # Non-mutation subcommand (git log, git diff, etc.) — advance past git block.
        i = j
        continue

    # sed / awk in-place: next arg is the -i flag.
    if INPLACE_RE.match(basename):
        if i + 1 < len(tokens) and INPLACE_FLAG_RE.match(tokens[i + 1]):
            print("BLOCK:inplace-edit:" + basename)
            sys.exit(0)

    # perl / ruby / php inline execution: -e or -i flag (may be combined: -pe).
    if basename in ("perl", "ruby", "php"):
        for flag in tokens[i+1:]:
            if not flag.startswith("-"):
                break
            if re.match(r"^-[^-]*[ei]", flag):
                print("BLOCK:inline-exec:" + basename)
                sys.exit(0)

    # python -c: block if exact "-c" token appears anywhere after the python binary.
    # Simple scan (not value-aware) is intentionally conservative: any python
    # invocation that includes a bare "-c" token is blocked regardless of
    # intervening flags like -W, -X, -B, -O.  Tokens like "-mpy_compile" never
    # equal exactly "-c" after shlex tokenization, so no false positives on -m flags.
    if PYTHON_RE.match(basename):
        if "-c" in tokens[i + 1:]:
            print("BLOCK:python-c")
            sys.exit(0)

    # Redirect that creates/clobbers a file: >file or >>file.
    # ALLOW: target is /dev/null, >&N, &>, 2>&1 (fd-dup forms).
    # The `>` shell metachar is its own token after shlex (when unquoted).
    # Quoted > (e.g. in a string) would not appear as a bare > token.
    if tok in (">", ">>"):
        if i + 1 < len(tokens):
            target = tokens[i + 1]
            # Allow /dev/null and fd-dup forms (&1, &2, etc.)
            if target == "/dev/null" or re.match(r"^&\d+$", target):
                i += 2
                continue
        print("BLOCK:redirect-to-file")
        sys.exit(0)

    # Compound redirect tokens like >file, >>file (shlex keeps these together
    # when the > is attached to the filename without spaces).
    if re.match(r"^>>?[^>]", tok):
        target = tok.lstrip(">")
        if target == "/dev/null" or re.match(r"^&\d+$", target):
            i += 1
            continue
        # Fd-dup forms like 2>&1 appear as a whole token.
        if re.match(r"^\d*>>?&\d+$", tok):
            i += 1
            continue
        print("BLOCK:redirect-to-file:" + tok)
        sys.exit(0)

    i += 1

print("ALLOW")
')

    case "$verdict" in
      ALLOW) ;;
      BLOCK:*)
        echo "auto-pilot: BLOCKED reviewer ($role) Bash — ${verdict#BLOCK:}" >&2
        exit 2
        ;;
      *)
        # Unexpected verdict — fail closed.
        echo "auto-pilot: BLOCKED reviewer ($role) Bash — unexpected verdict: $verdict (fail-closed)" >&2
        exit 2
        ;;
    esac

    if printf '%s' "$input" | python3 -c '
import json, sys
d = json.load(sys.stdin)
cmd = (d.get("tool_input") or {}).get("command", "")
print(cmd)
' 2>/dev/null | grep -qE '(^|[[:space:]])codex([[:space:]]|$)'; then
      cmd_for_codex=$(printf '%s' "$input" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print((d.get("tool_input") or {}).get("command", ""))
' 2>/dev/null || true)
      if ! printf '%s' "$cmd_for_codex" | grep -qE -- '--sandbox[[:space:]]+read-only'; then
        echo "auto-pilot: BLOCKED codex invocation without --sandbox read-only: $cmd_for_codex" >&2
        exit 2
      fi
    fi
    ;;
esac
exit 0

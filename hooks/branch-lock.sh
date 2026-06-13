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

# Bypass is honored ONLY from the real process/session env
# (export AUTO_PILOT_MAIN_OK=1 before launching the session).
# A tool-call command-string prefix such as
# `AUTO_PILOT_MAIN_OK=1 git push origin main` is NOT honored: the env-prefix
# in the Bash command string never reaches the hook subprocess env, and
# accepting it as a bypass string would make the guard self-grantable by any
# subagent that prepends the literal token.  Under an active auto-pilot run
# (AUTO_PILOT_HEADLESS=1 / HARNESS_HEADLESS=1) a push/commit without the
# real env token is DENIED — already the behavior here since the deny() path
# is the default for protected branches.
if [[ "${AUTO_PILOT_MAIN_OK:-0}" == "1" ]]; then
  exit 0
fi

# Determine working directory: use tool_input.cwd if present, else CWD.
#
# Worktree note (p3b 2026-06-13, NO-OP-CONFIRMED):
# A linked worktree has a .git FILE in its root; git -C <wt-dir> already
# resolves to the worktree branch natively.  When the hook subprocess CWD is
# the worktree directory (no payload.cwd), $(pwd) IS the worktree dir and git
# resolves correctly — no walk-up logic is needed.  When payload.cwd is set
# to the worktree dir (normal Claude Code Bash tool shape), S1 handles it.
# The "bare push from main-repo CWD with no payload.cwd" case is DENIED by
# design: that invocation is genuinely ambiguous (session root is on main).
# Override: AUTO_PILOT_MAIN_OK=1 or pass -C <wt-dir> in the git command.
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
# STRATEGY SHIFT (fixwave 2026-06-10): tokenize with shlex instead of a
# regex/str.split() tokenizer.  shlex.split() removes shell quoting so
# `git push origin "main"` / `'main'` yield the bare token `main`; subshell
# `()` / brace-group `{}` / separator `;` punctuation is stripped from the
# command before tokenizing so `(git push origin main)` and
# `{ git push origin main; }` are detected.  Fail-CLOSED: if shlex raises
# ValueError (unbalanced quotes) we still emit a conservative __CURRENT__
# push so a malformed push can't slip the lock.
#
# r5 contract preserved: push gates on DST refspec, not HEAD branch.
# Residual (documented): multiple -C compose in git; we honour the last only.
# shellcheck disable=SC2016 # python heredoc — $ and backtick are regex literals, not shell expansions
invocations=$(printf '%s' "$cmd" | python3 -c '
import os, sys, re, shlex

cmd = sys.stdin.read()

# Whether the raw command even mentions a git push/commit — used for the
# fail-closed path if shlex cannot parse the (likely malformed) string.
# \b already matches after ^, /, and backslash (all non-word chars); re.S so
# a malformed MULTILINE command (git\npush + unbalanced quote) still trips it.
_mentions = re.search(r"\bgit\b.*\b(push|commit)\b", cmd, re.S) is not None

# Fail CLOSED on shell-evaluation constructs a static tokenizer cannot resolve:
# command-substitution $(...) / backtick, variable expansion ($VAR / ${VAR}),
# or nested-shell (eval / sh -c / bash -c).  A push/commit command containing
# any of these is treated as a push to a PROTECTED branch (deny; the
# AUTO_PILOT_MAIN_OK bypass already exited earlier for legit overrides).  Closes
# the command-substitution evasion `$(printf git) push origin main` (codex
# re-review 2026-06-10) without per-case whack-a-mole: unanalyzable push = deny.
# Scope: only PUSH.  A push dst can be obscured by a construct, but a commit
# gates on the current HEAD read from git directly (the command string cannot
# lie about it), so a construct in a non-push command (`echo $(date); git
# status`, the `--skip-git-repo-check` flag, a feature-branch commit) is NOT
# failed closed — avoids over-firing on the common `$(...)` + non-push case.
# Include ANSI-C ($\x27) and locale ($") quoting alongside $(, ${, $VAR.
# \x27 = single-quote; avoids bash string-nesting issues (this Python is
# inside a bash single-quoted string).
_eval_construct = re.search(r"\$[\w({\x27\"]|`|\beval\b|\b(?:ba|z)?sh\s+-c\b", cmd)
if _eval_construct:
    # 1. Literal "push" word present alongside a construct → fail closed.
    if re.search(r"\bpush\b", cmd):
        print("push NONE main")
        sys.exit(0)
    # 2. Word-building: a construct delimiter directly adjacent to word chars
    #    (e.g. p$(...)h, $(cmd)push, pu${X}sh) means the construct is
    #    fragmenting a token — cannot resolve statically, fail closed when
    #    "git" also appears.  Catches the `p$(printf us)h` evasion (codex r2).
    _word_build = re.search(
        r"\w\$\([^)]*\)|\$\([^)]*\)\w"
        r"|\w\$\{[^}]*\}|\$\{[^}]*\}\w"
        r"|\w`[^`]*`|`[^`]*`\w", cmd)
    if _word_build and re.search(r"\bgit\b", cmd):
        print("push NONE main")
        sys.exit(0)

# Normalize backslash-newline continuations (shell line continuation) so the
# tokens rejoin: `git push origin \\\nmain` → `git push origin main`.
cmd = cmd.replace("\\\n", "")

# Strip subshell / brace-group / compound-separator punctuation so a wrapped
# invocation tokenizes the same as a bare one.  These are shell metacharacters,
# never part of a remote/refspec token.
sanitized = re.sub(r"[(){}]", " ", cmd)
sanitized = re.sub(r"&&|\|\||[;&|\n]", " ", sanitized)

try:
    all_tokens = shlex.split(sanitized)
    parse_ok = True
except ValueError:
    all_tokens = []
    parse_ok = False

if not parse_ok:
    # Fail closed: a push/commit we could not parse is treated as a bare
    # push against the current HEAD so the bash layer still gates on branch.
    if _mentions:
        print("push NONE __CURRENT__")
    sys.exit(0)

# shlex flattened the whole command into one token list (separators were
# replaced with spaces above).  Walk it and segment on each "git" boundary so
# multiple chained git invocations are each evaluated.
VALUE_TAKING = {"-o", "--push-option", "--repo", "--exec", "--receive-pack"}

# Find indices where a git invocation begins.
# Match both bare "git" and path-qualified "/usr/bin/git", "./git", etc.
git_starts = [k for k, t in enumerate(all_tokens)
              if os.path.basename(t.lstrip("\\\\")) == "git"]
for gi, gstart in enumerate(git_starts):
    gend = git_starts[gi + 1] if gi + 1 < len(git_starts) else len(all_tokens)
    tokens = all_tokens[gstart:gend]
    if not tokens:
        continue

    # Collect global options (flags and their arguments), then find subcommand
    i = 1
    c_path = None
    while i < len(tokens):
        t = tokens[i]
        if t == "-C" and i + 1 < len(tokens):
            c_path = tokens[i + 1]
            i += 2
        elif t.startswith("-c") and not t.startswith("--"):
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
    rest = tokens[i + 1:]

    c_str = c_path if c_path is not None else "NONE"

    if subcmd == "commit":
        print(f"commit {c_str}")
    elif subcmd == "push":
        positionals = []
        has_mirror_or_all = False
        j = 0
        while j < len(rest):
            t = rest[j]
            if t in VALUE_TAKING:
                j += 2
            elif t in ("--mirror", "--all"):
                has_mirror_or_all = True
                j += 1
            elif t.startswith("-"):
                j += 1
            else:
                positionals.append(t)
                j += 1
        # --mirror / --all push ALL branches; emit __ALL__ so the bash
        # layer checks whether ANY local branch is protected.
        if has_mirror_or_all:
            print(f"push {c_str} __ALL__")
        elif len(positionals) <= 1:
            print(f"push {c_str} __CURRENT__")
        else:
            for refspec in positionals[1:]:
                if refspec.startswith("+"):
                    refspec = refspec[1:]
                dst = refspec.split(":", 1)[1] if ":" in refspec else refspec
                # Case-insensitive strip of refs/heads/ prefix
                if dst.lower().startswith("refs/heads/"):
                    dst = dst[len("refs/heads/"):]
                # Also strip refs/remotes/ paths
                elif dst.lower().startswith("refs/remotes/"):
                    dst = dst[len("refs/remotes/"):]
                    # e.g. refs/remotes/origin/main → strip "origin/"
                    if "/" in dst:
                        dst = dst.split("/", 1)[1]
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
    if [[ "$dst" == "__ALL__" ]]; then
      # --mirror / --all: check if ANY local branch is protected.
      all_branches=$(git -C "$target" branch --format='%(refname:short)' 2>/dev/null || echo "")
      while IFS= read -r b; do
        lc_b=$(printf '%s' "$b" | tr '[:upper:]' '[:lower:]')
        if [[ "$lc_b" == "main" || "$lc_b" == "master" ]]; then
          deny "Refusing git push --mirror/--all: repo contains protected branch '$b' (target: $target). Set AUTO_PILOT_MAIN_OK=1 in the session env (export, not a command prefix) to override."
        fi
      done <<< "$all_branches"
      continue
    elif [[ "$dst" == "__CURRENT__" || "$dst" == "HEAD" ]]; then
      # Distinguish real git failure from legitimate empty (detached HEAD).
      # Detached HEAD → branch is empty string → lc_branch is "" → no deny.
      # git error (bad CWD, corrupt repo) → fail CLOSED with a clear message.
      branch=$(git -C "$target" branch --show-current 2>/tmp/bl_git_err) || {
        deny "branch-lock: git branch --show-current failed in $target ($(cat /tmp/bl_git_err 2>/dev/null | head -1)). Cannot verify branch; denying as a safety measure."
      }
    else
      branch="$dst"
    fi
  else
    # commit: gate on current HEAD
    # Fail CLOSED on genuine git error (bad CWD, corrupt repo, etc.).
    branch=$(git -C "$target" branch --show-current 2>/tmp/bl_git_err) || {
      deny "branch-lock: git branch --show-current failed in $target ($(cat /tmp/bl_git_err 2>/dev/null | head -1)). Cannot verify branch; denying as a safety measure."
    }
  fi

  # Case-insensitive comparison: Main/MAIN/MaIn all match.
  lc_branch=$(printf '%s' "$branch" | tr '[:upper:]' '[:lower:]')
  if [[ "$lc_branch" == "main" || "$lc_branch" == "master" ]]; then
    deny "Refusing git commit/push on protected branch '$branch' (target: $target). Set AUTO_PILOT_MAIN_OK=1 in the session env (export, not a command prefix) to override."
  fi
done <<< "$invocations"

exit 0

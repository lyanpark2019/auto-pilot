#!/usr/bin/env bash
# adversarial-review-loop helper functions.
#
# These use bash arrays — they BREAK if sourced into zsh (the common macOS
# interactive shell). ALWAYS invoke under bash, two supported ways:
#   1. CLI dispatch (pure fns):   bash arl-helpers.sh <arl_function> [args...]
#   2. chain that needs cd:       bash -c '. arl-helpers.sh; arl_worktree_ensure <slug> && codex exec ...'
# Every function returns non-zero on failure (set -e friendly).
# Portable to bash 3.2 (macOS): no associative arrays, no ${x,,}.

set -o pipefail

# --- baseline / preflight -------------------------------------------------

# Print conflict markers under a path; never fails on "no matches".
# usage: arl_conflict_markers [path]
arl_conflict_markers() {
  local path="${1:-.}"
  grep -rn '^<<<<<<< \|^=======$\|^>>>>>>> ' \
    --include='*' --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv \
    "$path" || true
}

# Print "behind<TAB>ahead" vs upstream; degrade gracefully with no upstream.
# usage: arl_ahead_behind
arl_ahead_behind() {
  local up
  up=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)
  if [ -n "$up" ]; then
    git rev-list --left-right --count "$up"...HEAD
  else
    echo "no upstream (new branch)"
  fi
}

# --- activation gate ------------------------------------------------------

# Succeed (0) iff src_dir has >= threshold files.
# usage: arl_repo_size_ok <src_dir> [threshold]
arl_repo_size_ok() {
  local src_dir="$1" threshold="${2:-200}" count
  [ -n "$src_dir" ] || { echo "arl_repo_size_ok: src_dir required" >&2; return 2; }
  count=$(find "$src_dir" -type f 2>/dev/null | wc -l | tr -d ' ')
  [ "$count" -ge "$threshold" ]
}

# --- contracts ------------------------------------------------------------

# Print the scope_files entries (one per line) declared in a contract md.
# Recognizes a "scope_files:" line followed by "- path" list items, or an
# inline "scope_files: [a, b, c]" array.
# usage: arl_parse_scope_files <contract_file>
arl_parse_scope_files() {
  local f="$1"
  [ -f "$f" ] || { echo "arl_parse_scope_files: no such file: $f" >&2; return 2; }
  awk '
    /^[[:space:]]*scope_files:[[:space:]]*\[/ {
      line=$0
      sub(/^[^[]*\[/, "", line); sub(/\].*$/, "", line)
      n=split(line, a, ",")
      for (i=1;i<=n;i++){ gsub(/^[[:space:]"'"'"']+|[[:space:]"'"'"']+$/, "", a[i]); if (a[i]!="") print a[i] }
      next
    }
    /^[[:space:]]*scope_files:[[:space:]]*$/ { inblk=1; next }
    inblk==1 {
      if ($0 ~ /^[[:space:]]+-[[:space:]]*/) {
        item=$0; sub(/^[[:space:]]+-[[:space:]]*/, "", item)
        gsub(/^[[:space:]"'"'"']+|[[:space:]"'"'"']+$/, "", item)
        if (item!="") print item
      } else if ($0 ~ /^[^[:space:]]/) { inblk=0 }
    }
  ' "$f"
}

# Resolve the contract file path for a slug (glob, first match).
# usage: arl_contract_path <slug> [contracts_dir]
arl_contract_path() {
  local slug="$1" dir="${2:-.planning/quality/contracts}" hit
  [ -n "$slug" ] || { echo "arl_contract_path: slug required" >&2; return 2; }
  hit=$(find "$dir" -maxdepth 1 -name "contract-*-${slug}.md" -print 2>/dev/null | head -n 1)
  [ -n "$hit" ] || { echo "arl_contract_path: no contract for slug=$slug" >&2; return 1; }
  printf '%s\n' "$hit"
}

# Group contracts that share any scope_file (conflict groups).
# Prints one group per line as space-separated slugs. Slugs sharing >=1 file
# land in the same line; disjoint slugs get their own line.
# usage: arl_conflict_groups [contracts_dir]
arl_conflict_groups() {
  local dir="${1:-.planning/quality/contracts}" f slug
  local slugs=() files=()   # parallel arrays: slugs[i] -> files[i] (space-joined)
  local i
  for f in "$dir"/contract-*.md; do
    [ -f "$f" ] || continue
    slug=$(basename "$f" .md); slug="${slug#contract-*-}"
    # strip leading "contract-NNN-" robustly
    slug=$(basename "$f" .md | sed 's/^contract-[0-9]*-//')
    local sf; sf=$(arl_parse_scope_files "$f" | tr '\n' ' ')
    slugs[${#slugs[@]}]="$slug"
    files[${#files[@]}]="$sf"
  done
  local n=${#slugs[@]}
  [ "$n" -gt 0 ] || return 0
  # group ids, init each to its own index
  local gid=() ; for ((i=0;i<n;i++)); do gid[i]=$i; done
  local a b x y shared
  for ((a=0;a<n;a++)); do
    for ((b=a+1;b<n;b++)); do
      shared=0
      for x in ${files[$a]}; do
        for y in ${files[$b]}; do
          if [ "$x" = "$y" ]; then shared=1; break; fi
        done
        [ "$shared" -eq 1 ] && break
      done
      if [ "$shared" -eq 1 ]; then
        # union: relabel all members of gid[b] to gid[a]
        local old=${gid[$b]} new=${gid[$a]} k
        for ((k=0;k<n;k++)); do [ "${gid[k]}" = "$old" ] && gid[k]=$new; done
      fi
    done
  done
  # emit one line per distinct group id
  local seen=" " g members j
  for ((i=0;i<n;i++)); do
    g=${gid[$i]}
    case "$seen" in *" g$g "*) continue;; esac
    seen="$seen g$g "
    members=""
    for ((j=0;j<n;j++)); do [ "${gid[$j]}" = "$g" ] && members="$members ${slugs[$j]}"; done
    echo "${members# }"
  done
}

# --- worktree lifecycle ---------------------------------------------------

# Path convention for a slug's worktree.
arl_worktree_path() { printf '%s\n' ".worktrees/quality-$1"; }

# Idempotently ensure a worktree on branch quality/<slug>, cd into it, assert branch.
# - reuse existing worktree dir
# - else attach existing branch
# - else create branch from <base> (default origin/main)
# Aborts (non-zero) if the resulting branch != quality/<slug>.
# Sourced use: cd persists in caller. usage: arl_worktree_ensure <slug> [base]
arl_worktree_ensure() {
  local slug="$1" base="${2:-origin/main}" wt cur
  [ -n "$slug" ] || { echo "arl_worktree_ensure: slug required" >&2; return 2; }
  wt=".worktrees/quality-$slug"
  if [ -d "$wt" ]; then
    cd "$wt" || return 1
  elif git show-ref --verify --quiet "refs/heads/quality/$slug"; then
    git worktree add "$wt" "quality/$slug" >&2 && cd "$wt" || return 1
  else
    git worktree add "$wt" -b "quality/$slug" "$base" >&2 && cd "$wt" || return 1
  fi
  cur=$(git branch --show-current)
  if [ "$cur" != "quality/$slug" ]; then
    echo "arl_worktree_ensure: wrong branch in worktree: $cur != quality/$slug" >&2
    return 1
  fi
}

# Remove a codex worker's worktree (Claude Agent worktrees are harness-managed).
# usage: arl_worktree_cleanup <slug>
arl_worktree_cleanup() {
  local slug="$1" wt=".worktrees/quality-$1"
  [ -n "$slug" ] || return 2
  # --force: worker test runs leave untracked files (e.g. __pycache__);
  # plain remove refuses a "dirty" worktree. We are intentionally discarding it.
  git worktree remove --force "$wt" 2>/dev/null || git worktree prune || true
}

# --- PR / merge -----------------------------------------------------------

# Create the PR only if one for quality/<slug> doesn't already exist (idempotent).
# usage: arl_pr_create_idempotent <slug> <contract> [base]
arl_pr_create_idempotent() {
  local slug="$1" contract="$2" base="${3:-main}" existing
  [ -n "$slug" ] && [ -n "$contract" ] || { echo "arl_pr_create_idempotent: slug+contract required" >&2; return 2; }
  # `--head` is NOT a flag of `gh pr view`; use `gh pr list` for the existence check.
  existing=$(gh pr list --head "quality/$slug" --state open --json number -q '.[0].number' 2>/dev/null)
  if [ -n "$existing" ]; then
    echo "PR #$existing already open for quality/$slug"
    return 0
  fi
  gh pr create --base "$base" --head "quality/$slug" \
    --title "quality: $slug" --body-file "$contract"
}

# Local merge fallback when gh pr merge is blocked.
# Fetches the worker branch first so the ref is present. Prefers fast-forward;
# if main has advanced (parallel worktree branches all cut from the same base),
# falls back to a real merge — safe because conflict-groups guarantee parallel
# branches touch disjoint files.
# usage: arl_local_merge <slug>
arl_local_merge() {
  local slug="$1"
  [ -n "$slug" ] || return 2
  git fetch origin "quality/$slug" || return 1
  git switch main || return 1
  git pull --ff-only origin main || return 1
  git merge --ff-only "origin/quality/$slug" \
    || git merge --no-edit "origin/quality/$slug" \
    || return 1
  git push origin HEAD:main
}

# --- orchestration decisions (pure, testable) -----------------------------

# Map an APPROVE-gate choice to an action. Encodes the c/d distinction:
# c = skip remaining this iteration (NOT terminal); d = exit loop (terminal).
# usage: arl_approve_action <a|b|c|d>
arl_approve_action() {
  case "$1" in
    a) echo "approve_all" ;;
    b) echo "select_ids" ;;
    c) echo "skip_to_rescore" ;;   # continues loop via RESCORE→CHECK
    d) echo "exit_loop" ;;          # terminal
    *) echo "invalid" >&2; return 2 ;;
  esac
}

# CHECK-table termination. Only user-exit (d) is the user-stop terminal.
# usage: arl_check_termination <weighted> <target> <viable_count> <iteration> <max_iter> <user_exit:0|1>
# prints: DONE:target | DONE:plateau | DONE:max_iter | DONE:user_stop | CONTINUE
arl_check_termination() {
  local weighted="$1" target="$2" viable="$3" iter="$4" maxit="$5" user_exit="${6:-0}"
  [ "$user_exit" = "1" ] && { echo "DONE:user_stop"; return 0; }
  if awk "BEGIN{exit !($weighted >= $target)}" 2>/dev/null; then echo "DONE:target"; return 0; fi
  [ "$viable" -le 0 ] && { echo "DONE:plateau"; return 0; }
  [ "$iter" -ge "$maxit" ] && { echo "DONE:max_iter"; return 0; }
  echo "CONTINUE"
}

# Multi-agent activation gate (all three conditions).
# usage: arl_activation_gate <requested:0|1> <src_dir> <open_contracts> <approved_count>
# prints: MULTI_AGENT | FALLBACK
arl_activation_gate() {
  local requested="$1" src_dir="$2" open="$3" approved="$4"
  [ "$requested" = "1" ] || { echo "FALLBACK"; return 0; }
  if arl_repo_size_ok "$src_dir" 200 2>/dev/null || [ "${open:-0}" -ge 5 ]; then :; else echo "FALLBACK"; return 0; fi
  [ "${approved:-0}" -ge 3 ] || { echo "FALLBACK"; return 0; }
  echo "MULTI_AGENT"
}

# Wave plan from conflict groups: serialize WITHIN a group, parallelize ACROSS
# groups, capped at n_workers per wave. Prints "wave <k>: <slug> <slug> ...".
# usage: arl_dispatch_waves <contracts_dir> [n_workers]
arl_dispatch_waves() {
  local dir="$1" n="${2:-5}"
  [ "$n" -ge 1 ] 2>/dev/null || n=1
  local groups=() line
  while IFS= read -r line; do [ -n "$line" ] && groups[${#groups[@]}]="$line"; done <<EOF
$(arl_conflict_groups "$dir")
EOF
  local remaining=1 wave=0
  while [ "$remaining" -eq 1 ]; do
    remaining=0; wave=$((wave+1))
    local picks="" count=0 gi
    for ((gi=0; gi<${#groups[@]}; gi++)); do
      local g="${groups[$gi]}"
      [ -z "$g" ] && continue
      remaining=1
      if [ "$count" -lt "$n" ]; then
        local head="${g%% *}" rest=""
        case "$g" in *" "*) rest="${g#* }" ;; *) rest="" ;; esac
        groups[gi]="$rest"
        picks="$picks $head"; count=$((count + 1))
      fi
    done
    [ -n "$picks" ] && echo "wave $wave:$picks"
  done
  return 0
}

# --- CLI dispatch ---------------------------------------------------------
# When executed under bash (not sourced), run the named function with args.
# Guarantees bash semantics regardless of the caller's interactive shell.
#   bash arl-helpers.sh arl_dispatch_waves .planning/quality/contracts 5
if [ -n "${BASH_SOURCE:-}" ] && [ "${BASH_SOURCE[0]}" = "${0}" ]; then
  fn="${1:-}"; shift || true
  case "$fn" in
    arl_*) "$fn" "$@" ;;
    *) echo "usage: bash $(basename "$0") <arl_function> [args...]" >&2; exit 64 ;;
  esac
fi

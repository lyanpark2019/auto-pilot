#!/usr/bin/env bash
# ap-worktree.sh — isolate parallel/concurrent work in a dedicated git worktree.
#
# Why: when two sessions share ONE working tree, a `git checkout` in one flips
# the shared .git/HEAD — the other tree is suddenly on main, so branch-lock
# DENIES its commit (the tree really IS on main then), and uncommitted work can
# be clobbered. A linked worktree has its OWN HEAD; always drive git through
# `git -C <worktree>` so commit/push resolve the worktree branch, not the root
# HEAD, and pass branch-lock with no bypass.
#
# Usage:
#   bash scripts/ap-worktree.sh new   <slug>   # create <base>/<prefix><slug> on fix/<slug>-<date>
#   bash scripts/ap-worktree.sh done  <slug>   # remove that worktree (+ cleanup reminders)
#   bash scripts/ap-worktree.sh prune          # drop stale registrations + leftover dirs
#
# Env knobs (defaults match the documented convention; overridable for tests):
#   AP_WORKTREE_BASE      worktree parent dir          (default: /tmp)
#   AP_WORKTREE_PREFIX    dir-name prefix              (default: ap-)
#   AP_WORKTREE_BASE_REF  branch point for `new`       (default: origin/main)
#                         a ref WITHOUT a "/" is treated as LOCAL → no fetch
#                         (lets tests / offline runs branch off a local `main`).
#
# Exit codes: 0 = ok, 1 = usage/arg error, 2 = git operation failed.
set -euo pipefail

BASE="${AP_WORKTREE_BASE:-/tmp}"
PREFIX="${AP_WORKTREE_PREFIX:-ap-}"
BASE_REF="${AP_WORKTREE_BASE_REF:-origin/main}"

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "error: not inside a git repository" >&2
  exit 1
}

die()  { echo "error: $*" >&2; exit 2; }
note() { echo "$*"; }

wt_path() { printf '%s/%s%s' "$BASE" "$PREFIX" "$1"; }

cmd_new() {
  local slug="$1"
  [[ -n "$slug" ]] || { echo "usage: ap-worktree.sh new <slug>" >&2; exit 1; }
  local wt branch
  wt="$(wt_path "$slug")"
  branch="fix/${slug}-$(date +%Y%m%d)"
  [[ -e "$wt" ]] && die "$wt already exists — pick another slug or run: ap-worktree.sh done $slug"

  # Refresh the base ONLY for a remote ref (contains '/'); a local ref (no '/')
  # is used as-is so tests / offline runs branch off a local main.
  if [[ "$BASE_REF" == */* ]]; then
    local remote rbranch
    remote="${BASE_REF%%/*}"
    rbranch="${BASE_REF#*/}"
    git -C "$REPO" fetch "$remote" "$rbranch" -q || die "fetch $BASE_REF failed"
  fi

  git -C "$REPO" worktree add -b "$branch" "$wt" "$BASE_REF" || die "worktree add failed"

  note "worktree: $wt"
  note "branch:   $branch"
  note ""
  note "Drive ALL git through -C (resolves the worktree branch, not the root HEAD):"
  note "  git -C $wt add -A && git -C $wt commit -F <msgfile>   # body via -F, not inline (branch-lock scans the command string)"
  note "  gh auth switch --hostname github.com --user <you>     # standalone, BEFORE push (preflight fail-closes a compound assert)"
  note "  git -C $wt push -u origin $branch                     # explicit refspec gates on dst, not HEAD"
  note "When merged:  bash scripts/ap-worktree.sh done $slug"
}

cmd_done() {
  local slug="$1"
  [[ -n "$slug" ]] || { echo "usage: ap-worktree.sh done <slug>" >&2; exit 1; }
  local wt
  wt="$(wt_path "$slug")"
  [[ -d "$wt" ]] || die "no worktree at $wt"

  local branch
  branch="$(git -C "$wt" branch --show-current 2>/dev/null || echo "")"

  local err
  err="$(git -C "$REPO" worktree remove "$wt" 2>&1)" || {
    echo "error: worktree remove failed: $err" >&2
    echo "  (uncommitted changes? commit/stash via 'git -C $wt ...' then re-run)" >&2
    exit 2
  }
  note "removed worktree: $wt"

  if [[ -n "$branch" ]]; then
    note ""
    note "branch '$branch' is no longer checked out. After its PR merges:"
    note "  git branch -D $branch    # guard-destructive marker: touch the printed marker, then re-run the IDENTICAL command"
    note "  gh api -X DELETE repos/<owner>/<repo>/git/refs/heads/$branch   # if the remote ref lingers"
  fi
}

cmd_prune() {
  # 1. Drop registrations whose worktree dir no longer exists.
  git -C "$REPO" worktree prune
  # 2. Remove leftover <base>/<prefix>* dirs that are not registered. Compare by
  #    BASENAME — `git worktree list` reports canonical paths (macOS /tmp ->
  #    /private/tmp), so a full-path compare would false-prune a live worktree.
  local registered
  registered="$(git -C "$REPO" worktree list --porcelain \
    | awk '/^worktree /{n=$2; sub(/.*\//,"",n); print n}')"
  local removed=0 d name
  for d in "$BASE/$PREFIX"*; do
    [[ -d "$d" ]] || continue
    name="$(basename "$d")"
    if ! printf '%s\n' "$registered" | grep -qxF "$name"; then
      rm -rf "$d"
      note "pruned stale dir: $d"
      removed=$((removed + 1))
    fi
  done
  if [[ "$removed" -eq 0 ]]; then
    note "prune: no stale $BASE/$PREFIX* dirs"
  fi
  return 0
}

main() {
  local sub="${1:-}"
  case "$sub" in
    new)   shift; cmd_new   "${1:-}" ;;
    done)  shift; cmd_done  "${1:-}" ;;
    prune) cmd_prune ;;
    *) echo "usage: ap-worktree.sh <new|done|prune> [slug]" >&2; exit 1 ;;
  esac
}

main "$@"

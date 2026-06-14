# PR merge serialization via flock(merge.lock)

Design proposal for swarm M2 race-hardening (written pre-merge for the standalone
autopilot-swarm plugin; paths updated to the merged auto-pilot layout). Target file:
`${CLAUDE_PLUGIN_ROOT}/swarm/scripts/run-pm.sh`
(scoring + merge stanza — the `# 1. score newly-done tickets` loop and the `# 2. ledger reconcile` call in run-pm.sh's main `while true` loop, ~lines 170–201 today).

Proposal only — **no shell edits in this ticket**. Implementation ticket must
verify every one-liner under [Acceptance hooks](#acceptance-hooks).

Source guidance:

- `synthesis.md` **T14** "Cross-repo / cross-worktree merge race" — Obsidian
  `sportic365-content failure-modes` row 4 + Web `augmentcode.com worktree
  guide`.
- `topics.json` entry `merge-lock-flock` (difficulty 4, scope
  `scripts/run-pm.sh`, goal_theme `race-conditions`).
- `external-web.md` §A.1 "mkdir vs flock — the canonical debate" (HN
  #35882629, BashFAQ/045) — `flock(2)` is kernel-backed, `mkdir` is the
  reliable portable fallback.
- `external-web.md` §E.3 — multiple worktrees share `.git/objects`; the
  race surface for autopilot is concurrent **`gh pr merge --squash`** calls
  against `origin/main`.
- `roadmap.json` M2 success_criterion (verbatim):
  - `grep -Eq 'flock|merge\.lock' scripts/run-pm.sh`

## Problem

`run-pm.sh:171–190` iterates `$ROOT/done/*.json`, scores each ticket, runs an
optional verifier when `verdict=="merge"`, then archives. The actual GitHub
PR merge call (`gh pr merge --squash --delete-branch …`) is delegated to the
`pm-ledger.md` prompt (`pm_call pm-ledger.md …` under the `# 2. ledger reconcile` anchor at run-pm.sh:194).

Today the PM merges tickets **sequentially within one PM tick** — safe. The
race appears in two realistic scenarios:

1. **Concurrent PM ticks.** Operator runs `start.sh` twice (different
   project, same fork), or `pm-ledger` re-enters via the `sleep 30; exec
   "$0"` retry path while a prior `gh pr merge` is mid-flight. Two
   `gh pr merge` invocations against the same `main` branch produce
   non-fast-forward churn — the second merge sees `main` already advanced,
   GitHub auto-rebases, the squash SHA differs from what the PM ledger
   recorded, and `pm-ledger.md`'s "winner cherry-pick" step lands the wrong
   SHA (synthesis T14).

2. **Worker auto-merge skill running alongside PM.** The `swarm` skill
   `ticket` subcommand comment at `run-pm.sh:204` already acknowledges a co-writer to `inbox/`.
   The same co-writer pattern leaks into the merge path when a worker is
   permitted to self-merge (future M5 scope) — without serialization, two
   merges race.

The repo already has a **dispatch** lock (`$LOCKDIR`,
`$ROOT/ledger/dispatch.lock.d`, line 14 (LOCKDIR) + lines 48–60 (acquire_lock/release_lock/trap)) that only guards inbox
writes. There is **no lock around the merge stanza**, and the dispatch lock
is the wrong primitive (different concern, different file, mkdir-based with
30s stale-clear and no PID stamp — see synthesis T3).

## Constraints

- Must run on **macOS + Linux**. macOS ships **no `flock(1)`** by default;
  Linux distros ship `util-linux flock` at `/usr/bin/flock`. Probe before
  use; fall back to a `mkdir`-based lock when missing.
- **Single host only.** flock and mkdir-locks are both fs-local; on NFS the
  serialization guarantees collapse silently (HN #35882629 thread, also
  `flock(2)` man page on Linux). The swarm targets a single
  workstation today — out-of-scope to support clustered runners.
- Hold time must be ≤ 60 s (the actual `gh pr merge --squash` round-trip is
  3–10 s in practice; 60 s covers a slow GitHub Actions required-check
  re-poll). Longer holds will starve subsequent PMs.
- Must not regress the existing `acquire_lock` / `release_lock` /
  `trap release_lock EXIT` shape (`run-pm.sh:48–60`). The new lock is a
  **second**, independent lock — distinct file, distinct trap entry.
- Must keep `set -euo pipefail` compatible (no unguarded `$?` after a `||`).

## Design

Add a dedicated merge-only lock at
`$ROOT/locks/merge.lock` (`$ROOT` = `$PROJECT/.planning/autopilot`).

Wrap the merge-effecting call (`pm_call pm-ledger.md …`, since that is what
issues `gh pr merge` today) in a `with_merge_lock` shell function that
detects `flock(1)` and falls back to `mkdir(2)`. Lock owner writes
`pid+ticket-id` into the lockfile for postmortem. Trap releases the lock on
EXIT/INT/TERM. Stale-lock cleanup at startup unlinks the mkdir variant when
the recorded PID is no longer alive.

### Exact bash snippet (for the implementation ticket)

To be inserted **near the top of `run-pm.sh`** (right after the `release_lock`
declaration at run-pm.sh:59), and the wrapper invocation goes around the
`pm-ledger.md` call at line 145.

```bash
# Merge serialization — independent of dispatch lock.
# See docs/architecture/merge-lock.md for rationale.
MERGE_LOCK_DIR="$ROOT/locks"
MERGE_LOCK="$MERGE_LOCK_DIR/merge.lock"
mkdir -p "$MERGE_LOCK_DIR"

# Startup stale-lock sweep: if mkdir-style dir lock exists and pid is dead, unlink.
if [ -d "${MERGE_LOCK}.d" ]; then
  _stale_pid="$(cat "${MERGE_LOCK}.d/owner.pid" 2>/dev/null || echo 0)"
  if ! kill -0 "$_stale_pid" 2>/dev/null; then
    rm -rf "${MERGE_LOCK}.d" || true
    echo "[pm] cleared stale merge.lock (pid=$_stale_pid dead)" | tee -a "$LOG"
  fi
fi

with_merge_lock() {
  local tid="${1:-unknown}"; shift || true
  if command -v flock >/dev/null 2>&1; then
    exec 9>"$MERGE_LOCK"
    if ! flock -w 60 9; then
      echo "[pm] merge.lock flock timeout (tid=$tid)" | tee -a "$LOG"
      exec 9>&-
      return 1
    fi
    printf '%s %s\n' "$$" "$tid" >&9
    "$@"
    local rc=$?
    exec 9>&-
    return "$rc"
  fi
  # macOS fallback: atomic mkdir lock with PID stamp + 60s wait budget.
  local tries=0
  until mkdir "${MERGE_LOCK}.d" 2>/dev/null; do
    tries=$((tries+1))
    if [ "$tries" -gt 60 ]; then
      echo "[pm] merge.lock mkdir timeout (tid=$tid)" | tee -a "$LOG"
      return 1
    fi
    sleep 1
  done
  printf '%s\n' "$$" > "${MERGE_LOCK}.d/owner.pid"
  printf '%s\n' "$tid" > "${MERGE_LOCK}.d/owner.tid"
  "$@"
  local rc=$?
  rm -rf "${MERGE_LOCK}.d" || true
  return "$rc"
}

# Released by trap on signal exit.
_merge_lock_cleanup() { rm -rf "${MERGE_LOCK}.d" 2>/dev/null || true; }
trap '_merge_lock_cleanup; release_lock' EXIT INT TERM
```

Invocation around the existing merge stanza (line 145 region):

```bash
# 2. ledger reconcile + cherry-pick winners — serialized via merge.lock.
with_merge_lock "ledger" pm_call pm-ledger.md "$ROOT/logs/ledger.log.tmp" PROJECT="$PROJECT"
cat "$ROOT/logs/ledger.log.tmp" >> "$ROOT/logs/ledger.log"
rm -f "$ROOT/logs/ledger.log.tmp"
```

`with_merge_lock` returns nonzero only on lock-acquire failure; the wrapped
command's exit status is propagated, so `pm_call`'s existing error path is
unchanged.

## Failure modes

1. **Stale lock after PM crash with `flock(1)`.** `flock(2)` is released by
   the kernel when fd 9 closes on process death — no operator action
   needed.
2. **Stale lock after PM crash on macOS fallback.** `${MERGE_LOCK}.d` stays
   on disk. Mitigated by the startup sweep (kills the directory if
   `owner.pid` is no longer alive). Worst case: operator deletes the dir
   manually — documented in README failure-mode table (M6 scope).
3. **`flock(1)` missing on macOS.** Detected via `command -v flock`. Falls
   back to mkdir variant — slower (1 s polling) but correct.
4. **NFS-hosted `$PROJECT`.** Both `flock` and `mkdir` lose atomicity on
   NFS without `lockd`. Emit a one-line warning in `pm.log` when
   `$PROJECT` filesystem type is `nfs`/`smbfs` (probe via `stat -f -c %T`
   on Linux, `stat -f -L%T` on macOS) and proceed best-effort. **Out of
   scope to enforce** — flag only.
5. **`with_merge_lock` invoked while caller already holds `$LOCKDIR`**
   (dispatch lock). Currently the two stanzas are disjoint
   (`pm-ledger.md` runs **before** `acquire_lock`/dispatch), so no nested
   acquisition. If a future refactor reorders, the trap chain
   `_merge_lock_cleanup; release_lock` still releases both — but
   documentation must call out lock ordering: **merge.lock outer,
   dispatch.lock.d inner**, never the reverse.
6. **`flock -w 60` timeout under load.** Returns rc=1; PM logs
   `merge.lock flock timeout` and the ticket stays in `done/` for the
   next tick (existing retry shape). No data loss — the verdict file is
   already on disk.

## Acceptance hooks

Implementation ticket must pass all of these from the swarm subtree root
(`${CLAUDE_PLUGIN_ROOT}/swarm`):

```bash
# Roadmap M2 success_criterion verbatim
grep -Eq 'flock|merge\.lock' scripts/run-pm.sh

# This proposal's additional shape checks
grep -q 'MERGE_LOCK=' scripts/run-pm.sh
grep -q 'with_merge_lock' scripts/run-pm.sh
grep -q 'flock -w 60' scripts/run-pm.sh
grep -q 'mkdir "\${MERGE_LOCK}.d"' scripts/run-pm.sh
grep -q '_merge_lock_cleanup' scripts/run-pm.sh

# Trap chain must release both locks on signal exit
grep -Eq "trap '.*_merge_lock_cleanup.*release_lock' EXIT" scripts/run-pm.sh

# Smoke: script still parses
bash -n scripts/run-pm.sh
```

## Out of scope

- **No shell edits in this ticket** — proposal only. Implementation goes in
  a separate M2 ticket scoped to `scripts/run-pm.sh`.
- **No fallback for clustered / NFS runners.** Single-host assumption is
  durable for swarm v1; revisit when a multi-host deployment
  appears (none on the roadmap).
- **No GitHub branch-protection changes.** Branch protection (required
  reviews, linear-history enforcement) is a complementary defence layer
  that lives in GitHub settings, not in this repo; the merge.lock is the
  local serialization primitive only.
- **No change to dispatch lock** (`$LOCKDIR`,
  `$ROOT/ledger/dispatch.lock.d`). That is synthesis T3 / topic
  `flock-based-pm-lockdir` — a separate M2 ticket.
- **No `swarm ticket` subcommand changes.** If/when a worker skill earns merge
  rights (M5+), it must call into the same `with_merge_lock` wrapper or
  re-implement the same `merge.lock` semantics.

## Open questions

- **Lock filename: `merge.lock` vs `merge.lock.d`?** flock wants a file
  (fd 9 binds to a regular file); mkdir wants a directory. Proposal uses
  **`merge.lock`** as the flock target and **`merge.lock.d/`** as the
  mkdir target. Both literal strings appear in the script, satisfying the
  M2 grep and keeping the two implementations textually distinct.
- **Should `pm-score.md` (`run-pm.sh:176`) also be wrapped?** Scoring is
  read-only and does not push to `origin/main`. No — keep the lock scoped
  to merge-effecting calls only. Wider scope adds latency without payoff.
- **Hold time budget — 60 s vs 120 s?** GitHub required-checks can take
  60–90 s on a cold runner. 60 s matches the proposal; if the
  implementation ticket observes timeouts in CI, bump to 120 and revisit.

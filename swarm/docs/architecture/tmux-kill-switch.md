# tmux kill-switch + diagnostic-pane wiring

Design proposal for swarm M4 wiring (written pre-merge for the standalone
autopilot-swarm plugin; paths updated to the merged auto-pilot layout). Target files:
`${CLAUDE_PLUGIN_ROOT}/swarm/scripts/start.sh`,
`${CLAUDE_PLUGIN_ROOT}/swarm/scripts/stop.sh`,
`${CLAUDE_PLUGIN_ROOT}/agents/swarm-monitor.md`.

This doc is **proposal only** — no shell edits in this ticket. The
implementation ticket must verify every one-liner under
[Acceptance hooks](#acceptance-hooks).

Source guidance:

- `synthesis.md` **T8** "tmux session needs remain-on-exit + trap-based
  cleanup" — Web (Reddit `r/tmux #1okc5cz`) + project gap.
- `synthesis.md` **T15** "UX: kill-switch + status visibility" — wire
  `agents/swarm-monitor.md` as permanent tmux window; honor
  `.planning/autopilot/STOP`.
- `external-web.md` §C.1 (`#reddit-tmux-1okc5cz`) — most tmux daemon
  failures = missing `set -g remain-on-exit on` ⇒ crashed pane vanishes,
  no postmortem.
- `roadmap.json` M4 `success_criteria` (verbatim):
  - `grep -Eq '2>\s*\$?\{?LOG|logs/pm-.*\.err' scripts/run-pm.sh`
  - `grep -q 'remain-on-exit' scripts/start.sh`
  - `grep -q 'trap' scripts/stop.sh`
  - `grep -q 'swarm-monitor' scripts/start.sh`

This doc addresses the last three (the first is run-pm.sh log-split,
out of scope).

## Current state

`scripts/start.sh` tmux bootstrap region. `remain-on-exit` is now SHIPPED
per-window (`tmux set-option -t "$SESSION":auto -w remain-on-exit on` at
start.sh:118, and again for the `auto2` window at start.sh:134) — wired per-window
with `-w` scope, NOT the session-wide placement this proposal recommended below
(M4 `remain-on-exit` objective DONE). Still missing: no `swarm-monitor` pane
(`grep -q 'swarm-monitor' scripts/start.sh` returns no match today). The embedded
block below shows the pre-`remain-on-exit` bootstrap and is retained as historical
context; current line anchors are has-session=start.sh:110, new-session=start.sh:116,
select-layout=start.sh:144/145:

```bash
100  if tmux has-session -t "$SESSION" 2>/dev/null; then
101    echo "[start] session '$SESSION' exists. Attaching."
102  else
103    # window 1: pane 0 = PM
104    tmux new-session -d -s "$SESSION" -n auto -c "$PROJECT"
105    PM_PANE="$(tmux list-panes -t "$SESSION":auto -F '#{pane_id}' | head -1)"
106    run_in_pane "$PM_PANE" "PLUGIN_ROOT=$PLUGIN_ROOT bash $PLUGIN_ROOT/scripts/run-pm.sh"
107
108    CUR_WIN=auto
109    CUR_PANES=1            # PM occupies one slot in window 'auto'
110    for i in $WORKER_IDS; do
...
128    tmux select-layout -t "$SESSION":auto tiled >/dev/null
129    [ "$CUR_WIN" = "auto2" ] && tmux select-layout -t "$SESSION":auto2 tiled >/dev/null
130  fi
```

`scripts/stop.sh` already has a trap at line 21 (M4 criterion
`grep -q 'trap' scripts/stop.sh` is satisfied today):

```bash
 8  _stop_cleanup() {
 9    local lockdir="$PROJECT/.planning/autopilot/ledger/dispatch.lock.d"
10    if [ -d "$lockdir" ]; then
11      local lockholder_pid_file="$lockdir/lockholder.pid"
12      if [ ! -f "$lockholder_pid_file" ] || ! kill -0 "$(cat "$lockholder_pid_file")" 2>/dev/null; then
13        rm -rf "$lockdir" || true
14      fi
15    fi
16    tmux kill-session -t "$SESSION" 2>/dev/null || true
17    echo "cleanup done" >&2
18  }
19
20  # Guarantee lockdir + tmux cleanup even when stop.sh is interrupted mid-loop.
21  trap '_stop_cleanup' EXIT INT TERM
```

## Failure modes

1. **Worker pane vanishes on crash, no postmortem.** Default tmux closes
   the pane the instant the child exits non-zero. PM/worker stack trace
   scrolls off-screen before operator sees it. Root cause: no
   `remain-on-exit on`. Documented in `external-web.md#reddit-tmux-1okc5cz`.

2. **stop.sh trap fires but child workers outlive tmux kill.** The trap
   at `stop.sh:21` calls `tmux kill-session`, which only sends SIGHUP to
   pane PIDs. Long-running `claude -p` / `codex exec` subprocesses
   spawned by `run-worker.sh` can survive (per `external-web.md` §B.2
   `pkill -P $$` pattern). Result: orphan processes still hold the
   ticket lock after "cleanup done" prints.

3. **swarm-monitor agent is orphaned.** `agents/swarm-monitor.md` exists
   but is never spawned by `scripts/start.sh` (synthesis T15;
   `roadmap.json` M5 has fallback assertion
   `test ! -f agents/swarm-monitor.md || grep -q 'swarm-monitor' scripts/start.sh`).
   Operator who runs `/auto-pilot:swarm` gets no live
   dashboard pane.

4. **stop.sh trap recursion on Ctrl-C during cleanup.** Per
   `external-web.md` §B.1 (StackOverflow #69101971), `trap cleanup
   INT EXIT` re-fires when SIGINT hits mid-cleanup. `_stop_cleanup`
   lacks an internal `trap '' INT` guard, so a second Ctrl-C from an
   impatient operator can leave the lockdir half-removed.

5. **`remain-on-exit on` + Ctrl-C from stop.sh interaction.** stop.sh
   sends `C-c` to every pane then `kill-session`. With
   `remain-on-exit on`, panes whose child has already exited would stay
   in `[exited]` state through the `kill-session` step; if `kill-session`
   is skipped (e.g. trap path), the session never goes away.

## Proposed wiring

### (a) `remain-on-exit on` placement in scripts/start.sh

Set on the **session**, not per-window. Reason: M4 success_criterion
only requires the literal string `remain-on-exit` in start.sh, and a
session-wide setting reaches every window/pane (`auto`, `auto2`, future
`monitor`) without N writes. Place the call **immediately after
`tmux new-session -d -s "$SESSION"`** (start.sh:116), before any pane is
fed a command — so a worker that crashes before the operator attaches
also leaves its error.

The line also disables auto-respawn:

```bash
tmux set-option -t "$SESSION" remain-on-exit on
```

Pane title format helps `swarm-monitor` distinguish live vs dead:

```bash
tmux set-option -t "$SESSION" -g pane-border-status top
tmux set-option -t "$SESSION" -g pane-border-format \
  '#{pane_index}: #{pane_current_command}#{?pane_dead, [DEAD exit=#{pane_dead_status}],}'
```

(Optional; not required by M4 grep.)

### (b) stop.sh trap × remain-on-exit interaction

With `remain-on-exit on`, panes whose child has died are NOT removed by
tmux. `_stop_cleanup` already calls `tmux kill-session -t "$SESSION"`
which forcibly tears down the whole session regardless of pane death
state — the right primitive. No change to stop.sh required for the M4
grep, but two robustness adds are recommended for failure modes
#2 and #4:

- Inside `_stop_cleanup`, before `kill-session`, send a process-tree
  signal to capture orphaned `claude`/`codex` children:
  ```bash
  tmux list-panes -s -t "$SESSION" -F '#{pane_pid}' 2>/dev/null \
    | while read -r p; do pkill -TERM -P "$p" 2>/dev/null || true; done
  ```
- First line of `_stop_cleanup`: `trap '' INT` to suppress re-entry
  during cleanup (StackOverflow #69101971).

These are **separate tickets** — out of scope for the M4-grep ticket
since `trap` already exists in stop.sh.

### (c) swarm-monitor placement

Spawn as **a dedicated tmux window** named `monitor` (NOT a pane in
`auto`), single pane index `0`. Reasons:

- `auto` window is tiled into 1 PM + ≤4 workers; adding a 6th pane
  forces a layout re-tile and breaks the 5-pane gate `[ "$CUR_PANES" -ge 5 ]`
  at start.sh:131.
- Monitor must survive a worker pane crash; a separate window is
  independent of `auto`'s pane lifecycle.
- `swarm-monitor.md` is read-only and outputs a single Markdown
  report, so a foreground `claude -p --agent swarm-monitor` loop with
  `sleep 30; clear; <re-run>` is appropriate (decision deferred — see
  [Open questions](#open-questions)).

The launch line goes immediately **before** `tmux select-layout` at
start.sh:144. It must contain the literal string `swarm-monitor` to satisfy
`grep -q 'swarm-monitor' scripts/start.sh`.

### Layout diagram

```
tmux session: autopilot-<basename>
│
├── window[0]  "auto"      (tiled, 5 panes max)
│     ┌──────────┬──────────┐
│     │ pane.0   │ pane.1   │
│     │ run-pm   │ worker-1 │
│     ├──────────┼──────────┤
│     │ pane.2   │ pane.3   │
│     │ worker-2 │ worker-3 │
│     ├──────────┴──────────┤
│     │       pane.4        │
│     │      worker-4       │
│     └─────────────────────┘
│
├── window[1]  "auto2"     (only if N>4 workers; tiled)
│     ┌──────────┬──────────┐
│     │ worker-5 │ worker-6 │ ...
│     └──────────┴──────────┘
│
└── window[2]  "monitor"   (single pane, swarm-monitor agent)
      ┌─────────────────────┐
      │  pane.0             │
      │  claude -p          │
      │  --agent            │
      │  swarm-monitor      │
      │  (re-render 30s)    │
      └─────────────────────┘

remain-on-exit on  ⇒ any dead pane stays as "[exited]" with last 2K
                     scrollback until operator runs stop.sh.
```

## Patch sketch

Minimal additions to satisfy the two M4 greps that touch start.sh
(`remain-on-exit` and `swarm-monitor`). Three lines total. **DO NOT
apply.**

```diff
--- a/scripts/start.sh
+++ b/scripts/start.sh
@@ -102,6 +102,7 @@ if tmux has-session -t "$SESSION" 2>/dev/null; then
 else
   # window 1: pane 0 = PM
   tmux new-session -d -s "$SESSION" -n auto -c "$PROJECT"
+  tmux set-option -t "$SESSION" remain-on-exit on
   PM_PANE="$(tmux list-panes -t "$SESSION":auto -F '#{pane_id}' | head -1)"
   run_in_pane "$PM_PANE" "PLUGIN_ROOT=$PLUGIN_ROOT bash $PLUGIN_ROOT/scripts/run-pm.sh"

@@ -125,6 +126,8 @@ else
     new_pane_with_cmd "$SESSION":$CUR_WIN "$CMD" >/dev/null
     CUR_PANES=$((CUR_PANES + 1))
   done
+  tmux new-window -t "$SESSION" -n monitor -c "$PROJECT"
+  tmux send-keys -t "$SESSION":monitor "claude -p --agent swarm-monitor 'health report; loop every 30s'" C-m
   tmux select-layout -t "$SESSION":auto tiled >/dev/null
   [ "$CUR_WIN" = "auto2" ] && tmux select-layout -t "$SESSION":auto2 tiled >/dev/null
 fi
```

## Acceptance hooks

Implementation ticket must pass all of these from the swarm subtree root
(`${CLAUDE_PLUGIN_ROOT}/swarm`):

```bash
# M4 success_criteria verbatim
grep -q 'remain-on-exit' scripts/start.sh
grep -q 'trap' scripts/stop.sh
grep -q 'swarm-monitor' scripts/start.sh

# This proposal's additional shape checks
grep -q 'tmux set-option -t "\$SESSION" remain-on-exit on' scripts/start.sh
grep -q 'tmux new-window -t "\$SESSION" -n monitor' scripts/start.sh
grep -q '\-\-agent swarm-monitor' scripts/start.sh

# Roadmap M5 fallback (orphan-cleanup guard)
test ! -f agents/swarm-monitor.md || grep -q 'swarm-monitor' scripts/start.sh

# Smoke: start.sh still parses
bash -n scripts/start.sh
bash -n scripts/stop.sh
```

## Open questions

- **remain-on-exit globally vs per-window?** Session-wide
  `set-option -t "$SESSION" remain-on-exit on` keeps the patch to one
  line, but it also freezes the future `monitor` window's pane on
  exit, which may confuse operators ("monitor crashed?"). Per-window
  alternative: `set-window-option -t "$SESSION":auto remain-on-exit on`
  plus the same for `auto2`. Trade-off: 2-3 lines vs explicit scope.
  Recommend session-wide for M4 simplicity; revisit if monitor pane
  death is noisy.

- **swarm-monitor as tmux pane vs background `claude -p` loop?**
  A tmux pane keeps the diagnostic output visible to the same operator
  who hits Ctrl-B; a background loop (`claude -p --agent swarm-monitor
  > .planning/autopilot/logs/monitor.log &`) is cheaper but invisible
  unless operator `tail -f`s. Recommend tmux pane (window `monitor`)
  because synthesis T15 framing is **"UX: status visibility"**, which
  implies a glance-able surface.

- **Should stop.sh send SIGTERM to pane child-trees before
  `kill-session`?** Failure mode #2 (orphan `claude`/`codex` children)
  is not covered by M4 grep but is implied by T8 mapping
  (`kill-children`). Decision belongs to a follow-up ticket once M4 is
  green.

- **Auto-attach the operator to `monitor` window?** Currently
  `start.sh:150` runs `exec tmux attach -t "$SESSION"`, which lands in
  `auto`. Switching default to `:monitor` would push diagnostic data
  first but hide PM/worker scroll. Recommend leaving default at `auto`
  and documenting `C-b 2` to flip to the monitor window in
  `README.md`.

- **Honor `.planning/autopilot/STOP` sentinel inside the monitor agent?**
  T4/T15 both reference a STOP file. Monitor is read-only, so it
  should *render* STOP state (e.g. row: "Kill-switch | ⚠️ STOP file
  present"), not act on it. Out of scope for M4 grep; flag for M5.

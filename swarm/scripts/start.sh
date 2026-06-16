#!/usr/bin/env bash
# auto-pilot swarm: bootstrap tmux session inside CURRENT terminal.
# Reads .planning/autopilot/config.json (created by /auto-pilot:swarm init).
# --no-attach: start detached (headless callers, e.g. bench.sh --auto-start).
set -euo pipefail

# 0. core-loop conflict guard — MUST run before sourcing the plugin lib so it
# fires unconditionally: the source below is an environment-dependent precondition
# (PLUGIN_ROOT may be absent on a fresh host), and a core-loop conflict must be
# reported regardless. They share the project tree; concurrent agentic mutations
# race git and the state schema.
_core_state="$(pwd)/.planning/auto-pilot/state.json"
if [ -f "$_core_state" ] && grep -q '"status"[[:space:]]*:[[:space:]]*"running"' "$_core_state"; then
  echo "swarm: refusing to start — core auto-pilot loop is running (state.json status=running)" >&2
  exit 3
fi

ATTACH=1
for arg in "$@"; do
  case "$arg" in
    --no-attach) ATTACH=0;;
  esac
done

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/auto-pilot}"
# shellcheck source=swarm/scripts/lib/swarm-models.sh
. "$PLUGIN_ROOT/swarm/scripts/lib/swarm-models.sh"
PROJECT="$(pwd)"
BASE="$(basename "$PROJECT")"
ROOT="$PROJECT/.planning/autopilot"
CONFIG="$ROOT/config.json"
SESSION="autopilot-$BASE"

# 1. config + git prerequisites
if [ ! -f "$CONFIG" ]; then
  echo "[start] no config at $CONFIG. Run /auto-pilot:swarm init first." >&2
  exit 2
fi
# `.git` is a directory in normal repos but a FILE inside worktrees.
# Use git plumbing instead of testing for the directory.
if ! git -C "$PROJECT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[start] $PROJECT is not a git repo. Run \`git init\` first." >&2
  exit 2
fi
# worktree-add HEAD needs at least one commit
if ! git -C "$PROJECT" rev-parse --verify HEAD >/dev/null 2>&1; then
  echo "[start] $PROJECT has no commits. Run \`git add <files> && git commit -m 'initial'\` first." >&2
  exit 2
fi
# git identity required for worker commits
if [ -z "$(git -C "$PROJECT" config user.email)" ] || [ -z "$(git -C "$PROJECT" config user.name)" ]; then
  echo "[start] git user.email/user.name not set. Run \`git config user.email <addr>\` and \`git config user.name <name>\`." >&2
  exit 2
fi

# 2. dependencies
for cmd in tmux jq envsubst claude codex git; do
  command -v "$cmd" >/dev/null || { echo "[start] missing dependency: $cmd (install: brew install $cmd; envsubst comes from gettext)" >&2; exit 3; }
done

# 2b. schema validation — every value that flows into bash/jq/tmux must be sane
schema_err() { echo "[start] invalid config: $1" >&2; exit 4; }
jq -e '(.pm.engine // "claude") == "claude" or (.pm.engine // "claude") == "codex"' "$CONFIG" >/dev/null \
  || schema_err 'pm.engine must be "claude" or "codex"'
jq -e --arg cm "$SWARM_PM_CLAUDE_MODEL" --arg crx "$SWARM_CODEX_MODEL_RE" '
  if (.pm.engine // "claude") == "claude" then (.pm.model // $cm) == $cm
  else (.pm.model // "gpt-5.5") | test($crx) end
' "$CONFIG" >/dev/null \
  || schema_err 'pm.model: claude→$SWARM_PM_CLAUDE_MODEL only; codex→gpt-5|gpt-5.5|o3'
jq -e '(.workers|type=="array") and (.workers|length>=4) and (.workers|length<=10)' "$CONFIG" >/dev/null \
  || schema_err 'workers must be array length 4..10'
jq -e '[.workers[].id] | (length == (unique|length))' "$CONFIG" >/dev/null \
  || schema_err 'worker ids must be unique'
jq -e --arg crx "$SWARM_CODEX_MODEL_RE" '.workers[] | (.id|type=="number") and (.engine=="claude" or .engine=="codex")
  and ((.engine=="claude" and (.model|startswith("claude-"))) or (.engine=="codex" and (.model|test($crx))))
  and ((.role|tostring) | test("^[a-z0-9][a-z0-9-]*$"))' "$CONFIG" >/dev/null \
  || schema_err 'each worker needs integer id, engine∈{claude,codex}, matching model (codex: gpt-5|gpt-5.5|o3), lowercase role tag'
jq -e '(.initial_goal.title|type=="string") and (.initial_goal.title|length>0) and (.initial_goal.title|length<=80)' "$CONFIG" >/dev/null \
  || schema_err 'initial_goal.title 1..80 chars required'
jq -e '(.initial_goal.success_criteria|type=="array") and (.initial_goal.success_criteria|length>=1)' "$CONFIG" >/dev/null \
  || schema_err 'initial_goal.success_criteria needs ≥1 entry'

# 3. message bus
mkdir -p "$ROOT"/{in_progress,done,scores,ledger,knowledge,archive,logs,bench}
WORKER_IDS=$(jq -r '.workers[].id' "$CONFIG")
for i in $WORKER_IDS; do
  mkdir -p "$ROOT/inbox/worker-$i" "$ROOT/outbox/worker-$i"
done
[ -f "$ROOT/ledger/agent-scores.json" ] || cat > "$ROOT/ledger/agent-scores.json" <<EOF
{"workers":{},"processed":[],"policy":{"incentive_threshold":40,"penalty_threshold":20,"weight_step":0.1,"weight_min":0.5,"weight_max":1.5}}
EOF

# 4. worktrees per worker
cd "$PROJECT"
for i in $WORKER_IDS; do
  WT="$PROJECT/../$BASE-worker-$i"
  BR="autopilot/worker-$i"
  if [ ! -d "$WT" ]; then
    echo "[start] git worktree add $WT ($BR)"
    git worktree add -B "$BR" "$WT" "$SWARM_BASE_BRANCH" >/dev/null
  fi
done

# 5. tmux session — 1 PM + N workers, split across windows if N>4
N=$(echo "$WORKER_IDS" | wc -l | tr -d ' ')

run_in_pane() {
  # $1=pane_id  $2=cmd
  tmux send-keys -t "$1" "$2" C-m
}

new_pane_with_cmd() {
  # echoes the new pane id; $1=window_target  $2=cmd
  local pane_id
  pane_id="$(tmux split-window -P -F "#{pane_id}" -t "$1" -c "$PROJECT")"
  tmux select-layout -t "$1" tiled >/dev/null
  run_in_pane "$pane_id" "$2"
  echo "$pane_id"
}

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[start] session '$SESSION' exists."
else
  # Clear any leftover STOP sentinel only when spawning a fresh session.
  rm -f "$ROOT/STOP"
  # window 1: pane 0 = PM
  tmux new-session -d -s "$SESSION" -n auto -c "$PROJECT"
  # Keep dead panes visible for postmortem debug.
  tmux set-option -t "$SESSION":auto -w remain-on-exit on
  PM_PANE="$(tmux list-panes -t "$SESSION":auto -F '#{pane_id}' | head -1)"
  run_in_pane "$PM_PANE" "PLUGIN_ROOT=$PLUGIN_ROOT bash $PLUGIN_ROOT/swarm/scripts/run-pm.sh"

  CUR_WIN=auto
  CUR_PANES=1            # PM occupies one slot in window 'auto'
  for i in $WORKER_IDS; do
    ENGINE=$(jq -r --argjson wid "$i" '.workers[] | select(.id==$wid) | .engine' "$CONFIG")
    MODEL=$(jq -r  --argjson wid "$i" '.workers[] | select(.id==$wid) | .model'  "$CONFIG")
    ROLE=$(jq -r   --argjson wid "$i" '.workers[] | select(.id==$wid) | .role'   "$CONFIG")
    CMD="PLUGIN_ROOT=$PLUGIN_ROOT bash $PLUGIN_ROOT/swarm/scripts/run-worker.sh $i $ENGINE $MODEL $ROLE"

    # need to start a 2nd window once first window is full (5 panes)
    if [ "$CUR_PANES" -ge 5 ] && [ "$CUR_WIN" = "auto" ]; then
      tmux new-window -t "$SESSION" -n auto2 -c "$PROJECT"
      # Keep dead panes visible for postmortem debug.
      tmux set-option -t "$SESSION":auto2 -w remain-on-exit on
      FIRST_PANE="$(tmux list-panes -t "$SESSION":auto2 -F '#{pane_id}' | head -1)"
      run_in_pane "$FIRST_PANE" "$CMD"
      CUR_WIN=auto2
      CUR_PANES=1
      continue
    fi
    new_pane_with_cmd "$SESSION":$CUR_WIN "$CMD" >/dev/null
    CUR_PANES=$((CUR_PANES + 1))
  done
  tmux select-layout -t "$SESSION":auto tiled >/dev/null
  [ "$CUR_WIN" = "auto2" ] && tmux select-layout -t "$SESSION":auto2 tiled >/dev/null
fi

echo "swarm online: $SESSION, $N workers"
if [ "$ATTACH" -eq 1 ]; then
  exec tmux attach -t "$SESSION"
fi
echo "[start] detached (--no-attach); observe with: tmux attach -t $SESSION"

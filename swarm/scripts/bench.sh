#!/usr/bin/env bash
# Benchmark: same task on swarm vs claude-solo vs codex-solo.
# usage: bench.sh "<task>" [--repeats N] [--swarm-timeout SEC] [--auto-start]
#        [--acceptance "<cmd>"] (repeatable; each appends one acceptance entry)
# --repeats N: run each arm N times; report median wall-time per arm.
# --auto-start: if no swarm session, launch one (detached) for arm A and
#   stop it again after arm A completes. Without it, arm A is skipped.
# --acceptance: shell command that exits 0 when the task succeeded.
#   Repeatable; omit to use the default non-empty-diff check.
set -euo pipefail
TASK="${1:?task required}"; shift

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=swarm/scripts/lib/bench-acceptance.sh
. "$SCRIPT_DIR/lib/bench-acceptance.sh"
# shellcheck source=swarm/scripts/lib/swarm-models.sh
. "$SCRIPT_DIR/lib/swarm-models.sh"

REPEATS=1
SWARM_TIMEOUT=1200
AUTO_START=0
ACCEPTANCE_JSON='[]'
ACCEPTANCE_COUNT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --repeats)        REPEATS="$2"; shift 2;;
    --swarm-timeout)  SWARM_TIMEOUT="$2"; shift 2;;
    --auto-start)     AUTO_START=1; shift;;
    --acceptance)
      if [ $# -lt 2 ]; then
        printf 'bench: --acceptance requires a value\n' >&2
        printf 'usage: bench.sh "<task>" [--repeats N] [--swarm-timeout SEC] [--auto-start] [--acceptance "<cmd>"]\n' >&2
        exit 1
      fi
      ACCEPTANCE_JSON="$(acceptance_append "$ACCEPTANCE_JSON" "$2")" || exit 1
      ACCEPTANCE_COUNT=$((ACCEPTANCE_COUNT + 1))
      shift 2;;
    --*)
      printf 'bench: unknown flag: %s\n' "$1" >&2
      printf 'usage: bench.sh "<task>" [--repeats N] [--swarm-timeout SEC] [--auto-start] [--acceptance "<cmd>"]\n' >&2
      exit 1;;
    *) shift;;
  esac
done

PROJECT="$(pwd)"
BASE="$(basename "$PROJECT")"
ROOT="$PROJECT/.planning/autopilot"
TS="$(date +%s)"
DIR="$ROOT/bench/$TS"
mkdir -p "$DIR"/{arm-a,arm-b,arm-c}
CONFIG="$ROOT/config.json"
SESSION="autopilot-$BASE"

if [ "$ACCEPTANCE_COUNT" -gt 0 ]; then
  acceptance_json="$ACCEPTANCE_JSON"
else
  acceptance_json="$(build_acceptance_json)"
fi

# ---------------------------------------------------------------------------
# median <val1> <val2> ... — prints integer median of space-separated values
# ---------------------------------------------------------------------------
median() {
  local sorted
  sorted=$(printf '%s\n' "$@" | sort -n)
  local count
  count=$(printf '%s\n' "$@" | wc -l | tr -d ' ')
  local mid
  mid=$(( (count + 1) / 2 ))
  printf '%s\n' "$sorted" | sed -n "${mid}p"
}

run_arm_solo() {
  local arm="$1" engine="$2" model="$3" rep="$4"
  local wt="$PROJECT/../$BASE-bench-$arm-$TS-r$rep"
  git -C "$PROJECT" worktree add -B "bench/$arm/$TS/r$rep" "$wt" HEAD >/dev/null
  local t0 t1
  t0=$(date +%s)
  cd "$wt"
  case "$engine" in
    claude) timeout 600 claude --model "$model" -p --dangerously-skip-permissions "$TASK" > "$DIR/arm-$arm/log-r$rep.md" 2>&1 || true;;
    codex)  timeout 600 codex exec --model "$model" -c model_reasoning_effort="xhigh" --sandbox workspace-write --skip-git-repo-check "$TASK" > "$DIR/arm-$arm/log-r$rep.md" 2>&1 || true;;
  esac
  t1=$(date +%s)
  git -C "$wt" add -A; git -C "$wt" commit -m "bench arm $arm r$rep" --allow-empty >/dev/null
  if git -C "$wt" rev-parse HEAD~1 >/dev/null 2>&1; then
    git -C "$wt" diff HEAD~1 HEAD > "$DIR/arm-$arm/diff-r$rep.patch" 2>/dev/null || true
  else
    git -C "$wt" diff "$(git -C "$wt" hash-object -t tree /dev/null)" HEAD > "$DIR/arm-$arm/diff-r$rep.patch" 2>/dev/null || true
  fi
  echo "$((t1-t0))" >> "$DIR/arm-$arm/wall_seconds_all"
  cd "$PROJECT"
}

run_arm_swarm() {
  local rep="$1"
  # id MUST match ticket.schema.json pattern ^T-[0-9]{8}-[0-9]{6}$ —
  # validate-ticket.sh rejects anything else before the worker runs.
  local id
  id="$(date +%Y%m%d-%H%M%S)"
  local target_worker engine role
  target_worker="$(jq -r '.workers[0].id' "$CONFIG")"
  engine="$(jq -r '.workers[0].engine' "$CONFIG")"
  role="$(jq -r '.workers[0].role // "general"' "$CONFIG")"

  jq -n \
    --arg id "T-$id" \
    --arg prompt "$TASK" \
    --arg engine "$engine" \
    --arg role "$role" \
    --arg issued_at "$(date -u +%FT%TZ)" \
    --arg worktree "../$BASE-worker-$target_worker" \
    --argjson acceptance "$acceptance_json" \
    '{id:$id,topic:"bench",title:"BENCH",prompt:$prompt,scope_paths:["."],acceptance:$acceptance,engine_hint:$engine,role:$role,difficulty:1,issued_at:$issued_at,issued_by:"bench",worktree:$worktree}' \
    > "$ROOT/inbox/worker-$target_worker/T-$id.json"
  local t0 t1 t_now
  t0=$(date +%s)
  while [ ! -f "$ROOT/scores/T-$id.json" ]; do
    t_now=$(date +%s)
    local elapsed=$((t_now - t0))
    if [ "$elapsed" -ge "$SWARM_TIMEOUT" ]; then
      echo "timeout" > "$DIR/arm-a/skipped-r$rep"
      echo "$elapsed" >> "$DIR/arm-a/wall_seconds_all"
      return 0
    fi
    if [ -f "$ROOT/STOP" ]; then
      echo "stopped" > "$DIR/arm-a/skipped-r$rep"
      return 0
    fi
    sleep 10
  done
  t1=$(date +%s)
  cp "$ROOT/scores/T-$id.json" "$DIR/arm-a/score-r$rep.json"
  cp -r "$ROOT/results/T-$id" "$DIR/arm-a/result-r$rep" 2>/dev/null || true
  echo "$((t1-t0))" >> "$DIR/arm-a/wall_seconds_all"
  cp "$ROOT/scores/T-$id.json" "$DIR/arm-a/score.json"
}

# ---------------------------------------------------------------------------
# Run each arm REPEATS times
# ---------------------------------------------------------------------------

STARTED_SWARM=0
if ! tmux has-session -t "$SESSION" 2>/dev/null && [ "$AUTO_START" -eq 1 ]; then
  echo "[bench] --auto-start: launching swarm detached"
  if bash "$SCRIPT_DIR/start.sh" --no-attach; then
    STARTED_SWARM=1
  else
    echo "[bench] auto-start failed — arm-a will be skipped"
  fi
fi
if tmux has-session -t "$SESSION" 2>/dev/null; then
  for rep in $(seq 1 "$REPEATS"); do
    echo "[bench] arm-a: swarm (rep $rep/$REPEATS)"
    run_arm_swarm "$rep"
  done
else
  echo "[bench] swarm not running — skipping arm-a (solo arms still run)"
  echo "n/a (swarm not running)" > "$DIR/arm-a/skipped"
fi
if [ "$STARTED_SWARM" -eq 1 ]; then
  echo "[bench] --auto-start: stopping self-started swarm"
  bash "$SCRIPT_DIR/stop.sh" || true
fi

# Arm B: claude opus solo
for rep in $(seq 1 "$REPEATS"); do
  echo "[bench] arm-b: claude opus solo (rep $rep/$REPEATS)"
  run_arm_solo b claude "$SWARM_PM_CLAUDE_MODEL" "$rep"
done

# Arm C: codex solo
for rep in $(seq 1 "$REPEATS"); do
  echo "[bench] arm-c: codex solo (rep $rep/$REPEATS)"
  run_arm_solo c codex "$SWARM_CODEX_DEFAULT_MODEL" "$rep"
done

# Score arms b/c with quality-eval (last rep's worktree — representative)
for arm in b c; do
  WT="$PROJECT/../$BASE-bench-$arm-$TS-r$REPEATS"
  claude --model "$SWARM_PM_CLAUDE_MODEL" -p --dangerously-skip-permissions \
    "Run Skill(quality-eval) on $WT. Output the resulting score-state.json verbatim." \
    > "$DIR/arm-$arm/quality-eval.md" 2>&1 || true
done

# ---------------------------------------------------------------------------
# Aggregate: compute median wall time per arm
# ---------------------------------------------------------------------------
arm_median() {
  local f="$DIR/arm-$1/wall_seconds_all"
  if [ -f "$f" ] && [ -s "$f" ]; then
    # shellcheck disable=SC2046
    median $(cat "$f")
  else
    echo "n/a"
  fi
}

MED_A=$(arm_median a)
MED_B=$(arm_median b)
MED_C=$(arm_median c)

[ "$MED_A" != "n/a" ] && echo "$MED_A" > "$DIR/arm-a/wall_seconds"
[ "$MED_B" != "n/a" ] && echo "$MED_B" > "$DIR/arm-b/wall_seconds"
[ "$MED_C" != "n/a" ] && echo "$MED_C" > "$DIR/arm-c/wall_seconds"

cat > "$DIR/report.md" <<EOF
# Bench $TS

Task: $TASK
Repeats: $REPEATS

| Arm | Median Wall (s) | Notes |
|---|---|---|
| A swarm | $MED_A | $(jq -r '.total // "n/a"' "$DIR/arm-a/score.json" 2>/dev/null || echo n/a) |
| B claude-opus-solo | $MED_B | see arm-b/quality-eval.md |
| C codex-gpt5-solo | $MED_C | see arm-c/quality-eval.md |

Artifacts under $DIR/.
EOF

echo "bench complete: $DIR/report.md"

#!/usr/bin/env bash
# Benchmark: same task on swarm vs claude-solo vs codex-solo.
# usage: bench.sh "<task>" [--repeats N] [--swarm-timeout SEC]
set -euo pipefail
TASK="${1:?task required}"; shift
REPEATS=1
SWARM_TIMEOUT=1200
while [ $# -gt 0 ]; do
  case "$1" in
    --repeats) REPEATS="$2"; shift 2;;
    --swarm-timeout) SWARM_TIMEOUT="$2"; shift 2;;
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

run_arm_solo() {
  local arm=$1; local engine=$2; local model=$3
  local wt="$PROJECT/../$BASE-bench-$arm-$TS"
  git -C "$PROJECT" worktree add -B "bench/$arm/$TS" "$wt" HEAD >/dev/null
  local t0 t1
  t0=$(date +%s)
  cd "$wt"
  case "$engine" in
    claude) timeout 600 claude --model "$model" -p --dangerously-skip-permissions "$TASK" > "$DIR/arm-$arm/log.md" 2>&1 || true;;
    codex)  timeout 600 codex exec --model "$model" -c model_reasoning_effort="xhigh" --sandbox workspace-write --skip-git-repo-check "$TASK" > "$DIR/arm-$arm/log.md" 2>&1 || true;;
  esac
  t1=$(date +%s)
  git -C "$wt" add -A; git -C "$wt" commit -m "bench arm $arm" --allow-empty >/dev/null
  if git -C "$wt" rev-parse HEAD~1 >/dev/null 2>&1; then
    git -C "$wt" diff HEAD~1 HEAD > "$DIR/arm-$arm/diff.patch" 2>/dev/null || true
  else
    git -C "$wt" diff "$(git -C "$wt" hash-object -t tree /dev/null)" HEAD > "$DIR/arm-$arm/diff.patch" 2>/dev/null || true
  fi
  echo "$((t1-t0))" > "$DIR/arm-$arm/wall_seconds"
  cd "$PROJECT"
}

run_arm_swarm() {
  # inject a manual ticket and wait for its score
  local id="bench-$TS"
  local target_worker
  target_worker="$(jq -r '.workers[0].id' "$CONFIG")"
  jq -n \
    --arg id "T-$id" \
    --arg prompt "$TASK" \
    --arg issued_at "$(date -u +%FT%TZ)" \
    --arg worktree "../$BASE-worker-$target_worker" \
    '{id:$id,title:"BENCH",prompt:$prompt,scope_paths:["."],acceptance:["task addressed"],issued_at:$issued_at,issued_by:"bench",worktree:$worktree}' \
    > "$ROOT/inbox/worker-$target_worker/T-$id.json"
  local t0 t1 t_now
  t0=$(date +%s)
  while [ ! -f "$ROOT/scores/T-$id.json" ]; do
    t_now=$(date +%s)
    local elapsed=$((t_now - t0))
    if [ $elapsed -ge "$SWARM_TIMEOUT" ]; then
      echo "timeout" > "$DIR/arm-a/skipped"
      echo "$elapsed" > "$DIR/arm-a/wall_seconds"
      return 0
    fi
    if [ -f "$ROOT/STOP" ]; then
      echo "stopped" > "$DIR/arm-a/skipped"
      return 0
    fi
    sleep 10
  done
  t1=$(date +%s)
  cp "$ROOT/scores/T-$id.json" "$DIR/arm-a/score.json"
  cp -r "$ROOT/results/T-$id" "$DIR/arm-a/result" 2>/dev/null || true
  echo "$((t1-t0))" > "$DIR/arm-a/wall_seconds"
}

# Arm A: swarm (only meaningful if swarm running)
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "[bench] arm-a: swarm"
  run_arm_swarm
else
  echo "[bench] swarm not running — skipping arm-a (solo arms still run)"
  echo "n/a (swarm not running)" > "$DIR/arm-a/skipped"
fi

# Arm B: claude opus solo (timeout-bounded)
echo "[bench] arm-b: claude opus 4.7 solo"
run_arm_solo b claude claude-opus-4-7

# Arm C: codex gpt-5.5 solo (timeout-bounded)
echo "[bench] arm-c: codex gpt-5.5 solo"
run_arm_solo c codex gpt-5.5

# Score arms b/c with quality-eval (delegate to claude)
for arm in b c; do
  WT="$PROJECT/../$BASE-bench-$arm-$TS"
  claude --model claude-opus-4-7 -p --dangerously-skip-permissions \
    "Run Skill(quality-eval) on $WT. Output the resulting score-state.json verbatim." \
    > "$DIR/arm-$arm/quality-eval.md" 2>&1 || true
done

# Final report
cat > "$DIR/report.md" <<EOF
# Bench $TS

Task: $TASK
Repeats: $REPEATS

| Arm | Wall (s) | Notes |
|---|---|---|
| A swarm | $(cat $DIR/arm-a/wall_seconds 2>/dev/null || echo n/a) | $(jq -r '.total // "n/a"' $DIR/arm-a/score.json 2>/dev/null) |
| B claude-opus-solo | $(cat $DIR/arm-b/wall_seconds) | see arm-b/quality-eval.md |
| C codex-gpt5-solo | $(cat $DIR/arm-c/wall_seconds) | see arm-c/quality-eval.md |

Artifacts under $DIR/.
EOF

echo "bench complete: $DIR/report.md"

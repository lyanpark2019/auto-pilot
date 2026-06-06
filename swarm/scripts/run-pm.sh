#!/usr/bin/env bash
# PM loop. Always uses claude-opus-4-7. Bootstraps once, then forever:
# explore → goal-decompose → score → ledger → dispatch.
set -euo pipefail

PLUGIN_ROOT="${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/auto-pilot}}"
PROJECT="$(pwd)"
BASE="$(basename "$PROJECT")"
ROOT="$PROJECT/.planning/autopilot"
CONFIG="$ROOT/config.json"
PROMPTS="$PLUGIN_ROOT/swarm/scripts/prompts"
LOG="$ROOT/logs/pm.log"
LOCKDIR="$ROOT/ledger/dispatch.lock.d"
PM_ENGINE="$(jq -r '.pm.engine // "claude"' "$CONFIG")"
PM_MODEL="$(jq -r '.pm.model // (if .pm.engine == "codex" then "gpt-5.5" else "claude-opus-4-7" end)' "$CONFIG")"
mkdir -p "$ROOT/logs" "$ROOT/knowledge"

acquire_lock() {
  local tries=0
  until mkdir "$LOCKDIR" 2>/dev/null; do
    tries=$((tries+1))
    if [ "$tries" -gt 30 ]; then
      echo "[pm] stale lock — clearing" | tee -a "$LOG"
      rm -rf "$LOCKDIR"
    fi
    sleep 1
  done
}
release_lock() { rmdir "$LOCKDIR" 2>/dev/null || true; }
trap release_lock EXIT

# helper: invoke claude opus PM with envsubst-rendered prompt
# Usage: pm_call <template> <stdout_file> [VAR=val ...] [--require <file>]
# --require <file>  : after the call, fail (return 1) if <file> does not exist
pm_call() {
  local tpl="$1" out="$2"; shift 2
  local require=""
  local envvars=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --require) require="$2"; shift 2;;
      *) envvars+=("$1"); shift;;
    esac
  done
  local rendered
  rendered="$(env "${envvars[@]}" envsubst < "$PROMPTS/$tpl")"
  local rc
  case "$PM_ENGINE" in
    codex)
      codex exec --model "$PM_MODEL" -c model_reasoning_effort="xhigh" --sandbox workspace-write --skip-git-repo-check "$rendered" > "$out" 2>&1
      rc=$?
      ;;
    *)
      claude --model "$PM_MODEL" -p --dangerously-skip-permissions "$rendered" > "$out" 2>&1
      rc=$?
      ;;
  esac
  if [ "$rc" -ne 0 ]; then
    echo "[pm/$PM_ENGINE] $tpl exited nonzero ($rc)" | tee -a "$LOG"
    return 1
  fi
  if [ -n "$require" ] && [ ! -f "$require" ]; then
    echo "[pm] $tpl did not produce $require" | tee -a "$LOG"
    return 1
  fi
  return 0
}

cd "$PROJECT"
echo "[pm/$PM_ENGINE/$PM_MODEL] online project=$PROJECT" | tee -a "$LOG"

# Phase 0a: explorer (run once per project unless re-bootstrapped)
# Sentinel touched ONLY if required artifacts exist.
if [ ! -f "$ROOT/knowledge/.explored" ]; then
  echo "[pm] swarm-explorer: scanning project" | tee -a "$LOG"
  if pm_call pm-explore.md "$ROOT/knowledge/explore.log" PROJECT="$PROJECT" \
      --require "$ROOT/knowledge/project-snapshot.md" \
      --require "$ROOT/knowledge/project-files.json"; then
    touch "$ROOT/knowledge/.explored"
  else
    echo "[pm] explore incomplete — retry next loop" | tee -a "$LOG"
    sleep 30; continue 2>/dev/null || exec "$0"
  fi
fi

# Phase 0b: knowledge bootstrap (notebooklm + obsidian + context7 + web)
if [ ! -f "$ROOT/knowledge/.bootstrapped" ]; then
  echo "[pm] knowledge bootstrap (notebooklm/obsidian/context7/web)" | tee -a "$LOG"
  if pm_call pm-bootstrap.md "$ROOT/knowledge/bootstrap.log" PROJECT="$PROJECT" \
      --require "$ROOT/knowledge/synthesis.md" \
      --require "$ROOT/knowledge/topics.json"; then
    touch "$ROOT/knowledge/.bootstrapped"
  else
    echo "[pm] bootstrap incomplete — retry next loop" | tee -a "$LOG"
    sleep 30; exec "$0"
  fi
fi

# Phase 0c: decompose initial goal into roadmap of topics
if [ ! -f "$ROOT/knowledge/.goal-decomposed" ]; then
  echo "[pm] goal decomposition" | tee -a "$LOG"
  if pm_call pm-goal-decompose.md "$ROOT/knowledge/goal.log" PROJECT="$PROJECT" \
      --require "$ROOT/knowledge/roadmap.json"; then
    touch "$ROOT/knowledge/.goal-decomposed"
  else
    echo "[pm] goal decompose incomplete — retry next loop" | tee -a "$LOG"
    sleep 30; exec "$0"
  fi
fi

# Main loop
SELF_IMPROVE_TARGET="$(jq -r '.policy.self_improve_target // ""' "$CONFIG")"

while true; do
  # I3: STOP sentinel — exit cleanly between iterations.
  if [ -f "$ROOT/STOP" ]; then
    echo "[pm] STOP sentinel detected — exiting loop" | tee -a "$LOG"
    exit 0
  fi
  # 1. score newly-done tickets (with optional verifier pass)
  for TF in "$ROOT"/done/*.json; do
    [ -e "$TF" ] || continue
    TID="$(basename "$TF" .json)"
    if [ ! -f "$ROOT/scores/$TID.json" ]; then
      echo "[pm] score $TID" | tee -a "$LOG"
      pm_call pm-score.md "$ROOT/scores/$TID.md" \
        SCORE_TID="$TID" PROJECT="$PROJECT" \
        --require "$ROOT/scores/$TID.json" || { echo "[pm] keep $TID for retry" | tee -a "$LOG"; continue; }
      # verifier — independent second-opinion for high-stakes (verdict=merge)
      if jq -e '.verdict=="merge"' "$ROOT/scores/$TID.json" >/dev/null 2>&1 && \
         jq -e '.policy.verifier_enabled' "$CONFIG" >/dev/null 2>&1; then
        echo "[pm] verifier $TID" | tee -a "$LOG"
        pm_call pm-verify.md "$ROOT/scores/$TID.verify.md" SCORE_TID="$TID" PROJECT="$PROJECT" || true
      fi
    fi
    # only archive after a score file exists
    if [ -f "$ROOT/scores/$TID.json" ]; then
      mv "$TF" "$ROOT/archive/$TID.json"
    fi
  done

  # 2. ledger reconcile + cherry-pick winners
  pm_call pm-ledger.md "$ROOT/logs/ledger.log.tmp" PROJECT="$PROJECT"
  cat "$ROOT/logs/ledger.log.tmp" >> "$ROOT/logs/ledger.log"
  rm -f "$ROOT/logs/ledger.log.tmp"

  # 3. dispatch new tickets where inbox empty
  # Lock prevents race with `swarm-ticket` skill that may also write to inbox/.
  acquire_lock
  for i in $(jq -r '.workers[].id' "$CONFIG"); do
    if [ -z "$(ls "$ROOT"/inbox/worker-$i/*.json 2>/dev/null)" ]; then
      ENGINE_HINT=$(jq -r ".workers[] | select(.id==$i) | .engine" "$CONFIG")
      ROLE=$(jq -r ".workers[] | select(.id==$i) | .role" "$CONFIG")

      # Self-improve: every 4th dispatched ticket targets the plugin if a self_improve_target is set.
      USE_SELF_IMPROVE=0
      if [ -n "$SELF_IMPROVE_TARGET" ] && [ -d "$SELF_IMPROVE_TARGET" ]; then
        DISPATCH_COUNT=$(jq -r '(.dispatch_count // 0) | tonumber? // 0' "$ROOT/ledger/agent-scores.json")
        DISPATCH_COUNT=$((DISPATCH_COUNT + 1))
        tmp="$ROOT/ledger/agent-scores.json.tmp"
        jq --argjson n "$DISPATCH_COUNT" '.dispatch_count = $n' "$ROOT/ledger/agent-scores.json" > "$tmp" && mv "$tmp" "$ROOT/ledger/agent-scores.json"
        if [ $((DISPATCH_COUNT % 4)) -eq 0 ]; then USE_SELF_IMPROVE=1; fi
      fi

      if [ $USE_SELF_IMPROVE -eq 1 ]; then
        echo "[pm] self-improve dispatch → worker-$i (target=$SELF_IMPROVE_TARGET)" | tee -a "$LOG"
        pm_call pm-self-improve.md "$ROOT/logs/dispatch.log.tmp" \
          WORKER_ID="$i" ENGINE_HINT="$ENGINE_HINT" ROLE="$ROLE" \
          PROJECT="$PROJECT" SELF_IMPROVE_TARGET="$SELF_IMPROVE_TARGET" || true
      else
        echo "[pm] dispatch → worker-$i ($ENGINE_HINT/$ROLE)" | tee -a "$LOG"
        pm_call pm-dispatch.md "$ROOT/logs/dispatch.log.tmp" \
          WORKER_ID="$i" ENGINE_HINT="$ENGINE_HINT" ROLE="$ROLE" PROJECT="$PROJECT" || true
      fi
      cat "$ROOT/logs/dispatch.log.tmp" >> "$ROOT/logs/dispatch.log" 2>/dev/null || true
      rm -f "$ROOT/logs/dispatch.log.tmp"
    fi
  done
  release_lock

  sleep 20
done

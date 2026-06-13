#!/usr/bin/env bash
# PM loop. PM model from config (default = SWARM_PM_CLAUDE_MODEL). Bootstraps once, then forever:
# explore → goal-decompose → score → ledger → dispatch.
set -euo pipefail

PLUGIN_ROOT="${PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/auto-pilot}}"
# shellcheck source=swarm/scripts/lib/swarm-models.sh
. "$PLUGIN_ROOT/swarm/scripts/lib/swarm-models.sh"
PROJECT="$(pwd)"
ROOT="$PROJECT/.planning/autopilot"
CONFIG="$ROOT/config.json"
PROMPTS="$PLUGIN_ROOT/swarm/scripts/prompts"
LOG="$ROOT/logs/pm.log"
LOCKDIR="$ROOT/ledger/dispatch.lock.d"
PM_ENGINE="$(jq -r '.pm.engine // "claude"' "$CONFIG")"
PM_MODEL="$(jq -r --arg cm "$SWARM_PM_CLAUDE_MODEL" '.pm.model // (if .pm.engine == "codex" then "gpt-5.5" else $cm end)' "$CONFIG")"
PM_CALL_TIMEOUT_SEC="$(jq -r '.policy.pm_call_timeout_sec // 600' "$CONFIG")"
DISPATCH_BACKOFF_THRESHOLD="$(jq -r '.policy.dispatch_backoff_threshold // 3' "$CONFIG")"
DISPATCH_ABORT_THRESHOLD="$(jq -r '.policy.dispatch_abort_threshold // 10' "$CONFIG")"
VALIDATE_TICKET="$PLUGIN_ROOT/swarm/scripts/validate-ticket.sh"

# shellcheck source=swarm/scripts/lib/dispatch-backoff.sh
. "$PLUGIN_ROOT/swarm/scripts/lib/dispatch-backoff.sh"

mkdir -p "$ROOT/logs" "$ROOT/knowledge" "$ROOT/archive" "$ROOT/in_progress"

# Validate numeric config values; fall back to defaults on garbage input.
case "$PM_CALL_TIMEOUT_SEC" in
  (*[!0-9]*|'') echo "[pm] WARNING: pm_call_timeout_sec invalid — using 600" | tee -a "$LOG"; PM_CALL_TIMEOUT_SEC=600;;
esac
case "$DISPATCH_BACKOFF_THRESHOLD" in
  (*[!0-9]*|'') echo "[pm] WARNING: dispatch_backoff_threshold invalid — using 3" | tee -a "$LOG"; DISPATCH_BACKOFF_THRESHOLD=3;;
esac
case "$DISPATCH_ABORT_THRESHOLD" in
  (*[!0-9]*|'') echo "[pm] WARNING: dispatch_abort_threshold invalid — using 10" | tee -a "$LOG"; DISPATCH_ABORT_THRESHOLD=10;;
esac

# Resolve timeout binary once at startup (P2: portability + kill-after guard).
TIMEOUT_CMD=""
if command -v timeout >/dev/null 2>&1; then
  TIMEOUT_CMD="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
  TIMEOUT_CMD="gtimeout"
else
  echo "[pm] WARNING: timeout(1) not found — pm_call runs unwrapped" | tee -a "$LOG"
fi

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
  if [ -n "$TIMEOUT_CMD" ]; then
    case "$PM_ENGINE" in
      codex)
        "$TIMEOUT_CMD" -k 30 "$PM_CALL_TIMEOUT_SEC" \
          codex exec --model "$PM_MODEL" -c model_reasoning_effort="xhigh" --sandbox workspace-write --skip-git-repo-check "$rendered" > "$out" 2>&1
        rc=$?
        ;;
      *)
        "$TIMEOUT_CMD" -k 30 "$PM_CALL_TIMEOUT_SEC" \
          claude --model "$PM_MODEL" -p --dangerously-skip-permissions "$rendered" > "$out" 2>&1
        rc=$?
        ;;
    esac
  else
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
  fi
  if [ "$rc" -eq 124 ]; then
    echo "[pm/$PM_ENGINE] $tpl TIMEOUT after ${PM_CALL_TIMEOUT_SEC}s" | tee -a "$LOG"
    return 1
  fi
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
    sleep 30; exec "$0"
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
DISPATCH_FAILURES=0

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
  # P1: guard bare pm_call under set -e; also guard the following cat (tmp may not exist on timeout).
  if ! pm_call pm-ledger.md "$ROOT/logs/ledger.log.tmp" PROJECT="$PROJECT"; then
    echo "[pm] ledger failed — continuing" | tee -a "$LOG"
  else
    if [ -f "$ROOT/logs/ledger.log.tmp" ]; then
      cat "$ROOT/logs/ledger.log.tmp" >> "$ROOT/logs/ledger.log"
    fi
  fi
  rm -f "$ROOT/logs/ledger.log.tmp"

  # 3. dispatch new tickets where inbox empty
  # Lock prevents race with `swarm` skill `ticket` subcommand that may also write to inbox/.
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

      # Snapshot inbox BEFORE pm_call to detect worker-claimed files.
      # Newline-delimited to handle paths that contain spaces.
      # Also stamp a reference time used later to detect in_progress arrivals.
      INBOX_DIR="$ROOT/inbox/worker-$i"
      PRE_SNAPSHOT=""
      for pre_tf in "$INBOX_DIR"/*.json; do
        [ -e "$pre_tf" ] || continue
        PRE_SNAPSHOT="${PRE_SNAPSHOT}${pre_tf}
"
      done

      DISPATCH_STAMP="$ROOT/logs/.dispatch-stamp"
      touch "$DISPATCH_STAMP"

      DISPATCH_OK=0
      if [ $USE_SELF_IMPROVE -eq 1 ]; then
        echo "[pm] self-improve dispatch → worker-$i (target=$SELF_IMPROVE_TARGET)" | tee -a "$LOG"
        if pm_call pm-self-improve.md "$ROOT/logs/dispatch.log.tmp" \
            WORKER_ID="$i" ENGINE_HINT="$ENGINE_HINT" ROLE="$ROLE" \
            PROJECT="$PROJECT" SELF_IMPROVE_TARGET="$SELF_IMPROVE_TARGET"; then
          DISPATCH_OK=1
        fi
      else
        echo "[pm] dispatch → worker-$i ($ENGINE_HINT/$ROLE)" | tee -a "$LOG"
        if pm_call pm-dispatch.md "$ROOT/logs/dispatch.log.tmp" \
            WORKER_ID="$i" ENGINE_HINT="$ENGINE_HINT" ROLE="$ROLE" PROJECT="$PROJECT"; then
          DISPATCH_OK=1
        fi
      fi
      cat "$ROOT/logs/dispatch.log.tmp" >> "$ROOT/logs/dispatch.log" 2>/dev/null || true
      rm -f "$ROOT/logs/dispatch.log.tmp"

      if [ "$DISPATCH_OK" -eq 1 ]; then
        # P0/P3: Find ALL new tickets (not in pre-snapshot, not manual).
        # A worker may have claimed a pre-existing file during pm_call; exclude those.
        FOUND_VALID=0
        FOUND_ANY_NEW=0
        for tf in "$INBOX_DIR"/*.json; do
          [ -e "$tf" ] || continue
          # Skip T-manual-* tickets — PM didn't write them; never count or delete.
          if is_manual_ticket "$tf"; then
            continue
          fi
          # Check if this file was already present before pm_call.
          # Iterate newline-delimited PRE_SNAPSHOT to avoid word-split on spaces.
          was_pre=0
          while IFS= read -r pre_tf; do
            [ -z "$pre_tf" ] && continue
            if [ "$pre_tf" = "$tf" ]; then
              was_pre=1
              break
            fi
          done <<EOF_PRE
$PRE_SNAPSHOT
EOF_PRE
          [ "$was_pre" -eq 1 ] && continue
          # New file written by this dispatch.
          FOUND_ANY_NEW=1
          # Send validator stderr to LOG.
          if "$VALIDATE_TICKET" "$tf" >/dev/null 2>>"$LOG"; then
            FOUND_VALID=1
          else
            # P2: worker may have mv-claimed between the glob and validate.
            if [ ! -f "$tf" ]; then
              echo "[pm] dispatch worker-$i: claimed mid-validation — not a failure" | tee -a "$LOG"
              FOUND_VALID=1
            else
              TID_INV="$(basename "$tf" .json)"
              INVALID_PATH="$ROOT/archive/${TID_INV}.invalid.json"
              if mv "$tf" "$INVALID_PATH" 2>/dev/null; then
                echo "[pm] dispatch worker-$i: schema invalid → archived $INVALID_PATH" | tee -a "$LOG"
              else
                echo "[pm] dispatch worker-$i: schema invalid and mv failed (claimed?) — not a failure" | tee -a "$LOG"
                FOUND_VALID=1
              fi
            fi
          fi
        done

        if [ "$DISPATCH_OK" -eq 1 ] && [ "$FOUND_ANY_NEW" -eq 0 ]; then
          # Worker may have mv-claimed the ticket from inbox during pm_call's window.
          # Use find -newer stamp (stamp was touched immediately before pm_call)
          # so only genuinely new in_progress files (mtime after stamp) are counted.
          if find "$ROOT/in_progress" -type f -name '*.json' -newer "$DISPATCH_STAMP" | grep -q .; then
            echo "[pm] dispatch worker-$i: ticket claimed by worker during pm_call — not a failure" | tee -a "$LOG"
            FOUND_VALID=1
          else
            echo "[pm] dispatch worker-$i: no ticket produced" | tee -a "$LOG"
          fi
        fi

        DISPATCH_FAILURES="$(apply_dispatch_result 1 "$FOUND_VALID" "$DISPATCH_FAILURES")"
      else
        DISPATCH_FAILURES="$(apply_dispatch_result 0 0 "$DISPATCH_FAILURES")"
      fi

      if [ "$DISPATCH_FAILURES" -ge "$DISPATCH_ABORT_THRESHOLD" ]; then
        echo "[pm] dispatch abort: $DISPATCH_FAILURES consecutive failures — touching STOP (recover: stop.sh then start.sh, or rm $ROOT/STOP before next start)" | tee -a "$LOG"
        touch "$ROOT/STOP"
        release_lock
        exit 1
      fi

      if [ "$DISPATCH_FAILURES" -ge "$DISPATCH_BACKOFF_THRESHOLD" ]; then
        backoff_sec="$(compute_backoff_sec "$DISPATCH_FAILURES" "$DISPATCH_BACKOFF_THRESHOLD")"
        echo "[pm] dispatch backoff: $DISPATCH_FAILURES consecutive failures — sleeping ${backoff_sec}s" | tee -a "$LOG"
        release_lock
        sleep "$backoff_sec"
        acquire_lock
      fi
    fi
  done
  release_lock

  sleep 20
done

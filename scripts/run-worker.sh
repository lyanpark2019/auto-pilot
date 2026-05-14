#!/usr/bin/env bash
# usage: run-worker.sh <id> <claude|codex> <model> <role>
set -euo pipefail
ID="${1:?id}"; ENGINE="${2:?engine}"; MODEL="${3:?model}"; ROLE="${4:-general}"
PROJECT="$(pwd)"
BASE="$(basename "$PROJECT")"
WT="$PROJECT/../$BASE-worker-$ID"
ROOT="$PROJECT/.planning/autopilot"
INBOX="$ROOT/inbox/worker-$ID"
OUTBOX="$ROOT/outbox/worker-$ID"
LOG="$ROOT/logs/worker-$ID.log"

mkdir -p "$INBOX" "$OUTBOX" "$ROOT/in_progress" "$ROOT/done" "$ROOT/results"
[ -d "$WT" ] || { echo "[w$ID] missing worktree $WT" | tee -a "$LOG"; exit 1; }

echo "[w$ID/$ENGINE/$MODEL/$ROLE] online wt=$WT" | tee -a "$LOG"

while true; do
  TICKET="$(ls -t "$INBOX"/*.json 2>/dev/null | head -1 || true)"
  if [ -z "${TICKET:-}" ]; then sleep 8; continue; fi
  TID="$(basename "$TICKET" .json)"
  IP="$ROOT/in_progress/$TID.json"
  mv "$TICKET" "$IP"
  PROMPT="$(jq -r '.prompt' "$IP")"
  RESULT_DIR="$ROOT/results/$TID"; mkdir -p "$RESULT_DIR"
  echo "[w$ID] claim $TID" | tee -a "$LOG"

  cd "$WT"
  case "$ENGINE" in
    claude)
      claude --model "$MODEL" -p --dangerously-skip-permissions \
        "Working dir: $WT
Worker: $ID  Role: $ROLE  Engine: $ENGINE/$MODEL
Ticket: $TID

$PROMPT

Constraints: write only inside this worktree. Do not commit — outer loop commits." \
        > "$OUTBOX/$TID.md" 2>&1 || echo "[w$ID] claude exit nonzero" | tee -a "$LOG"
      ;;
    codex)
      codex exec --full-auto --skip-git-repo-check \
        "Working dir: $WT
Worker: $ID  Role: $ROLE  Engine: $ENGINE/$MODEL
Ticket: $TID

$PROMPT" \
        > "$OUTBOX/$TID.md" 2>&1 || echo "[w$ID] codex exit nonzero" | tee -a "$LOG"
      ;;
    *)
      echo "[w$ID] unknown engine $ENGINE" | tee -a "$LOG"
      ;;
  esac

  git -C "$WT" add -A
  git -C "$WT" diff --cached > "$RESULT_DIR/diff.patch" || true
  git -C "$WT" commit -m "autopilot: $TID" --allow-empty >/dev/null
  git -C "$WT" rev-parse HEAD > "$RESULT_DIR/commit.sha"

  mv "$IP" "$ROOT/done/$TID.json"
  echo "[w$ID] done $TID" | tee -a "$LOG"
done

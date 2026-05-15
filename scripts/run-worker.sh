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

# Optional auto-PR: only if `gh` is installed AND repo has an origin remote.
PR_ENABLED=0
command -v gh >/dev/null && git -C "$WT" remote get-url origin >/dev/null 2>&1 && PR_ENABLED=1

open_pr() {
  local TID="$1" TITLE="$2" BR="$3" RESULT_DIR="$4"
  [ "$PR_ENABLED" -eq 1 ] || { echo "[w$ID] PR skipped (gh missing or no origin)" | tee -a "$LOG"; return 0; }
  local AHEAD
  AHEAD="$(git -C "$WT" rev-list --count "main..$BR" 2>/dev/null || echo 0)"
  if [ "$AHEAD" -eq 0 ]; then
    echo "[w$ID] $TID — no commits vs main, skip PR" | tee -a "$LOG"
    return 0
  fi
  git -C "$WT" push -u origin "$BR" >> "$LOG" 2>&1 || {
    echo "[w$ID] push failed for $BR" | tee -a "$LOG"
    return 1
  }
  local BODY
  BODY="$(printf 'Autopilot ticket %s\n\nWorker: %s (engine=%s, model=%s, role=%s)\nWorktree: %s\n\nSee `.planning/autopilot/done/%s.json` for the ticket spec.\n' \
    "$TID" "$ID" "$ENGINE" "$MODEL" "$ROLE" "$WT" "$TID")"
  gh pr create \
    --repo "$(gh repo view --json nameWithOwner -q .nameWithOwner)" \
    --base main --head "$BR" \
    --title "autopilot[$TID]: $TITLE" \
    --body "$BODY" \
    >> "$LOG" 2>&1 || echo "[w$ID] gh pr create failed for $TID" | tee -a "$LOG"
  gh pr view "$BR" --json url -q .url > "$RESULT_DIR/pr.url" 2>/dev/null || true
}

while true; do
  # I3: STOP sentinel — exit cleanly between tickets if user dropped it.
  if [ -f "$ROOT/STOP" ]; then
    echo "[w$ID] STOP sentinel detected — exiting" | tee -a "$LOG"
    exit 0
  fi
  # I7: FIFO (oldest-first). ls -tr sorts by mtime ascending; head -1 = oldest.
  TICKET="$(ls -tr "$INBOX"/*.json 2>/dev/null | head -1 || true)"
  if [ -z "${TICKET:-}" ]; then sleep 8; continue; fi
  TID="$(basename "$TICKET" .json)"

  # I2: schema validation BEFORE atomic claim. Malformed → archive/<tid>.invalid.json, no engine call.
  if ! "$(dirname "$0")/validate-ticket.sh" "$TICKET" 2>>"$LOG"; then
    INVALID="$ROOT/archive/$TID.invalid.json"
    mkdir -p "$ROOT/archive"
    mv "$TICKET" "$INVALID" 2>/dev/null || true
    echo "[w$ID] reject $TID — schema invalid → $INVALID" | tee -a "$LOG"
    continue
  fi

  IP="$ROOT/in_progress/$TID.json"
  if ! mv "$TICKET" "$IP" 2>/dev/null; then
    echo "[w$ID] race-lost on $TID" | tee -a "$LOG"
    continue
  fi
  PROMPT="$(jq -r '.prompt' "$IP")"
  TITLE="$(jq -r '.title // .id' "$IP")"
  RESULT_DIR="$ROOT/results/$TID"; mkdir -p "$RESULT_DIR"
  echo "[w$ID] claim $TID" | tee -a "$LOG"

  cd "$WT"
  # Per-ticket branch off main so each PR is isolated (PR_ENABLED mode).
  if [ "$PR_ENABLED" -eq 1 ]; then
    BR="autopilot/$TID"
    git -C "$WT" fetch origin main --quiet >> "$LOG" 2>&1 || true
    git -C "$WT" checkout -B "$BR" origin/main >> "$LOG" 2>&1 || \
      git -C "$WT" checkout -B "$BR" main >> "$LOG" 2>&1
  else
    BR="autopilot/worker-$ID"
  fi
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
      # Top-tier model + xhigh reasoning explicit (subscription budget OK).
      # --sandbox workspace-write replaces deprecated --full-auto.
      codex exec --model "$MODEL" \
        -c model_reasoning_effort="xhigh" \
        --sandbox workspace-write \
        --skip-git-repo-check \
        "Working dir: $WT
Worker: $ID  Role: $ROLE  Engine: $ENGINE/$MODEL/xhigh
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
  git -C "$WT" commit -m "autopilot: $TID — $TITLE" --allow-empty >/dev/null
  git -C "$WT" rev-parse HEAD > "$RESULT_DIR/commit.sha"

  # Open PR if remote + gh available; no-op otherwise.
  open_pr "$TID" "$TITLE" "$BR" "$RESULT_DIR" || true

  mv "$IP" "$ROOT/done/$TID.json"
  echo "[w$ID] done $TID" | tee -a "$LOG"
done

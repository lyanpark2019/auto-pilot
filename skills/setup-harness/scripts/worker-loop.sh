#!/usr/bin/env bash
# worker-loop.sh — tmux pane polling loop for ONE Codex worker.
#
# Uses `codex exec` SYNC mode (NOT `codex-companion --background` — broker state
# is process-local; new CLI invocations cannot fetch prior job results).
#
# Required env:
#   WORKER_ID         — 1..N
#   PLANNING_DIR      — absolute path to .planning/harness-rewrite (under project_root)
# Optional env:
#   CODEX_MODEL       — default gpt-5.5
#   CODEX_EFFORT      — default xhigh
#   CODEX_TIMEOUT     — default 1200 (seconds)
#   POLL_INTERVAL     — default 8 (seconds)
#   ONE_SHOT          — if set, exit after processing 1 ticket (useful for tests)

set -euo pipefail

: "${WORKER_ID:?WORKER_ID required}"
: "${PLANNING_DIR:?PLANNING_DIR required (absolute path to .planning/harness-rewrite)}"

CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
CODEX_EFFORT="${CODEX_EFFORT:-xhigh}"
CODEX_TIMEOUT="${CODEX_TIMEOUT:-1200}"
POLL_INTERVAL="${POLL_INTERVAL:-8}"

INBOX="${PLANNING_DIR}/inbox/worker-${WORKER_ID}"
OUTBOX="${PLANNING_DIR}/outbox/worker-${WORKER_ID}"
DONE="${PLANNING_DIR}/done/worker-${WORKER_ID}"
mkdir -p "$INBOX" "$OUTBOX" "$DONE"

echo "[worker-${WORKER_ID}] polling ${INBOX} every ${POLL_INTERVAL}s (model=${CODEX_MODEL} effort=${CODEX_EFFORT})"

while true; do
  TICKET="$(ls -1tr "${INBOX}"/*.json 2>/dev/null | head -1 || true)"
  if [[ -z "$TICKET" ]]; then
    sleep "$POLL_INTERVAL"
    continue
  fi

  TICKET_BASE="$(basename "$TICKET" .json)"
  OUT_FILE="${OUTBOX}/${TICKET_BASE}.md"
  LOG_FILE="${OUTBOX}/${TICKET_BASE}.log"

  echo "[worker-${WORKER_ID}] $(date -u +%FT%TZ) claim ${TICKET_BASE}"

  # codex exec SYNC: stdin → stdout. NOT --background.
  if timeout "$CODEX_TIMEOUT" codex exec \
       --skip-git-repo-check \
       -s read-only \
       --color never \
       -c model="${CODEX_MODEL}" \
       -c model_reasoning_effort="${CODEX_EFFORT}" \
       - < "$TICKET" > "$OUT_FILE" 2> "$LOG_FILE"; then
    mv "$TICKET" "${DONE}/${TICKET_BASE}.json"
    echo "[worker-${WORKER_ID}] $(date -u +%FT%TZ) done ${TICKET_BASE} -> ${OUT_FILE} ($(wc -l < "$OUT_FILE") lines)"
  else
    echo "[worker-${WORKER_ID}] $(date -u +%FT%TZ) FAIL ${TICKET_BASE} (exit=$?) — see ${LOG_FILE}" >&2
    mv "$TICKET" "${INBOX}/.${TICKET_BASE}.failed.json"
  fi

  [[ -n "${ONE_SHOT:-}" ]] && break
done

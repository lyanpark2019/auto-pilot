#!/usr/bin/env bash
# codex-analyze.sh — Codex multi-worker analysis driver
#
# Implements the Opus-PM + Codex-worker supervisor pattern (see
# references/codex-multi-worker-doctrine.md). Uses `codex exec` sync mode,
# NOT `codex-companion --background` (broker state is process-local).
#
# Sub-commands:
#   init <project_root> [N=5]    Scaffold .planning/harness-rewrite/ + doctrine.md.
#   dispatch <ticket_file>       Run codex exec for one ticket (foreground; use & for parallel).
#   spawn <project_root> [N=5]   tmux mode: boot N+1 pane session (PM + N worker polling loops).
#   verify <outbox_dir>          Check frontmatter + path:line citation + wikilink count.
#   publish <vault_root>         Copy outbox + pm-draft into vault (after user gate).
#
# Two dispatch modes (both valid; pick per session):
#   A. Claude run_in_background — `dispatch` × N from a Claude Code session. Auto turn notification.
#                                 PM == this Claude session. Best for one-shot batches.
#   B. tmux pane                 — `spawn` then drop tickets into inbox/worker-N/. Pane polls + runs.
#                                 PM == operator at pane 0. Best for long-running ops, multi-session,
#                                 human-in-the-loop observation, or running outside Claude harness.
# See references/codex-multi-worker-doctrine.md for trade-offs.
#
# Required external: codex (CLI ≥0.130).
# Optional env: CODEX_MODEL (default gpt-5.5), CODEX_EFFORT (default xhigh), CODEX_TIMEOUT (default 1200).

set -euo pipefail

CODEX_MODEL="${CODEX_MODEL:-gpt-5.5}"
CODEX_EFFORT="${CODEX_EFFORT:-xhigh}"
CODEX_TIMEOUT="${CODEX_TIMEOUT:-1200}"

# Locate this skill's references/ directory regardless of caller cwd.
SKILL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTRINE_SRC="${SKILL_ROOT}/references/codex-multi-worker-doctrine.md"

usage() {
  sed -n '2,20p' "$0"
  exit 2
}

cmd_init() {
  local project_root="${1:?project_root required}"
  local n_workers="${2:-5}"
  local planning="${project_root}/.planning/harness-rewrite"

  if [[ ! -d "$project_root" ]]; then
    echo "ERROR: project_root not a directory: $project_root" >&2
    exit 1
  fi

  for sub in inbox outbox "done" refs pm-draft; do
    for i in $(seq 1 "$n_workers"); do
      [[ "$sub" == "pm-draft" ]] && break
      mkdir -p "${planning}/${sub}/worker-${i}"
    done
    [[ "$sub" == "pm-draft" ]] && mkdir -p "${planning}/pm-draft/principles"
  done
  mkdir -p "${planning}/refs"

  cp "$DOCTRINE_SRC" "${planning}/refs/doctrine.md"
  : > "${planning}/ledger.md"
  cat > "${planning}/ledger.md" <<EOF
# Harness Rewrite Ledger

PM activity log. Append-only.

| timestamp | event | detail |
|-----------|-------|--------|
| $(date -u +%FT%TZ) | init | scaffold ${n_workers} workers; doctrine copied from skill |
EOF

  echo "OK init: ${planning}"
  echo "Doctrine: ${planning}/refs/doctrine.md"
  echo "Ledger:   ${planning}/ledger.md"
  echo "Next: PM writes ticket JSON into inbox/worker-N/; then call: dispatch <ticket_file>"
}

cmd_dispatch() {
  local ticket="${1:?ticket_file required}"
  if [[ ! -f "$ticket" ]]; then
    echo "ERROR: ticket not found: $ticket" >&2
    exit 1
  fi

  # Derive worker number + ticket id from path.
  local worker_dir ticket_base outbox_dir planning
  worker_dir="$(dirname "$ticket")"          # .planning/.../inbox/worker-N
  planning="$(cd "${worker_dir}/../.." && pwd)"
  outbox_dir="${planning}/outbox/$(basename "$worker_dir")"
  done_dir="${planning}/done/$(basename "$worker_dir")"
  mkdir -p "$outbox_dir" "$done_dir"
  ticket_base="$(basename "$ticket" .json)"
  local out_md="${outbox_dir}/${ticket_base}.md"
  local out_log="${outbox_dir}/${ticket_base}.log"

  local doctrine_rel
  doctrine_rel=".planning/harness-rewrite/refs/doctrine.md"

  local prompt_file
  prompt_file="$(mktemp)"
  cat > "$prompt_file" <<EOF
You are a Codex worker invoked via the harness supervisor pattern.

MUST read first:
  - ${doctrine_rel}  (15 principles + 12 sources)
  - apply the Module / Interface / Seam / Depth / Leverage / Locality lens to every boundary

Ticket:
$(cat "$ticket")

Output a single Obsidian-compatible markdown deliverable to stdout. Start with YAML
frontmatter per the ticket's format spec. Use [[wikilinks]] for related vault pages.
Cite every fact as path:line. Apply deletion test: each paragraph must claim
something whose removal loses information.
EOF

  echo "[$(basename "$worker_dir")] dispatching ${ticket_base} (timeout=${CODEX_TIMEOUT}s)" >&2
  if timeout "$CODEX_TIMEOUT" codex exec \
       --skip-git-repo-check \
       -s read-only \
       --color never \
       -c model="${CODEX_MODEL}" \
       -c model_reasoning_effort="${CODEX_EFFORT}" \
       - < "$prompt_file" > "$out_md" 2> "$out_log"; then
    mv "$ticket" "${done_dir}/${ticket_base}.json"
    echo "[$(basename "$worker_dir")] OK ${ticket_base} -> ${out_md} ($(wc -l < "$out_md") lines)"
  else
    echo "[$(basename "$worker_dir")] FAIL ${ticket_base} (exit=$?) — see ${out_log}" >&2
    rm -f "$prompt_file"
    exit 1
  fi
  rm -f "$prompt_file"
}

cmd_spawn() {
  # Wrapper: tmux mode. Delegates to spawn-tmux.sh which uses worker-loop.sh per pane.
  local project_root="${1:?project_root required}"
  local n_workers="${2:-5}"
  local session="${3:-harness}"
  local spawn_script="${SKILL_ROOT}/scripts/spawn-tmux.sh"

  if [[ ! -x "$spawn_script" ]]; then
    echo "ERROR: ${spawn_script} not executable" >&2
    exit 1
  fi
  if [[ ! -d "${project_root}/.planning/harness-rewrite" ]]; then
    echo "ERROR: scaffold missing — run 'init ${project_root} ${n_workers}' first" >&2
    exit 1
  fi
  bash "$spawn_script" "$project_root" "$n_workers" "$session"
}

cmd_verify() {
  local outbox_dir="${1:?outbox_dir required}"
  if [[ ! -d "$outbox_dir" ]]; then
    echo "ERROR: outbox_dir not a directory: $outbox_dir" >&2
    exit 1
  fi

  local fail=0
  for f in "$outbox_dir"/*.md; do
    [[ -f "$f" ]] || continue
    local size citations wikilinks frontmatter
    size=$(wc -l < "$f" | tr -d ' ')
    citations=$(grep -oE '[a-zA-Z_./-]+\.(py|md|json|yaml|yml|sh):[0-9]+' "$f" | wc -l | tr -d ' ')
    wikilinks=$(grep -oE '\[\[[^]]+\]\]' "$f" | wc -l | tr -d ' ')
    head -1 "$f" | grep -q '^---$' && frontmatter=OK || frontmatter=MISS

    local row
    row="$(basename "$f") size=${size} citations=${citations} wikilinks=${wikilinks} frontmatter=${frontmatter}"
    if [[ "$frontmatter" == "MISS" || "$size" -lt 30 || "$citations" -lt 5 ]]; then
      echo "FAIL ${row}"
      fail=1
    else
      echo "OK   ${row}"
    fi
  done
  exit "$fail"
}

_ensure_vault_master_index() {
  # Creates vault_root/wiki/index.md from template on first publish; otherwise leaves it alone.
  local vault_root="$1"
  local master="${vault_root}/wiki/index.md"
  local template="${SKILL_ROOT}/templates/wiki-master-index.template.md"
  local project_name="$2"
  local date_now="$3"

  mkdir -p "${vault_root}/wiki"
  if [[ -f "$master" ]]; then
    echo "INFO master index exists: $master (leaving untouched)"
    return 0
  fi
  if [[ ! -f "$template" ]]; then
    echo "WARN master template missing: $template — skipping master creation" >&2
    return 0
  fi
  sed -e "s/{{PROJECT_NAME}}/${project_name}/g" -e "s/{{DATE}}/${date_now}/g" \
    "$template" > "$master"
  echo "OK created master index: $master"
}

_ensure_vault_top_pointer() {
  # Appends a wiki/ pointer to vault_root/_index.md if missing. Idempotent.
  local vault_root="$1"
  local top_index="${vault_root}/_index.md"
  local marker="\`wiki/\` — cross-project knowledge trees"

  [[ -f "$top_index" ]] || return 0
  if grep -qF "$marker" "$top_index"; then
    echo "INFO _index.md already references wiki/"
    return 0
  fi
  cat >> "$top_index" <<'POINTER'

<!-- codex-analyze insert -->
## wiki/

- `wiki/` — cross-project knowledge trees (Codex-authored, PM-curated). Entry: [[wiki/index]].

Run `bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/codex-analyze.sh init <repo>` to scaffold harness-engineering analysis tickets, then `publish` into `wiki/harness-engineering/`.
POINTER
  echo "OK appended wiki/ pointer to: $top_index"
}

cmd_publish() {
  local vault_root="${1:?vault_root required (typically ~/Documents/Obsidian/<project>-Vault)}"
  local project_root="${2:-$PWD}"
  local planning="${project_root}/.planning/harness-rewrite"
  local target="${vault_root}/wiki/harness-engineering"
  local project_name date_now
  project_name="$(basename "$project_root")"
  date_now="$(date -u +%F)"

  if [[ ! -d "$planning" ]]; then
    echo "ERROR: planning directory missing: $planning" >&2
    exit 1
  fi
  if [[ ! -d "$vault_root" ]]; then
    echo "ERROR: vault_root not found: $vault_root" >&2
    exit 1
  fi

  # Master index + vault top pointer (both idempotent).
  _ensure_vault_master_index "$vault_root" "$project_name" "$date_now"
  _ensure_vault_top_pointer "$vault_root"

  mkdir -p "${target}/principles" "${target}/layers"

  # PM-authored pages (canonical names expected in pm-draft).
  for f in index.md deepening-backlog.md; do
    [[ -f "${planning}/pm-draft/${f}" ]] && cp "${planning}/pm-draft/${f}" "${target}/${f}"
  done
  [[ -f "${planning}/refs/friction-map.md" ]] && cp "${planning}/refs/friction-map.md" "${target}/friction-map.md"

  for p in 01-doctrine 02-supervisor-pattern 03-message-bus; do
    if [[ -f "${planning}/pm-draft/principles/${p}.md" ]]; then
      cp "${planning}/pm-draft/principles/${p}.md" "${target}/principles/${p}.md"
    fi
  done
  # Fallback: copy doctrine straight from refs/ when PM hasn't customised.
  if [[ ! -f "${target}/principles/01-doctrine.md" && -f "${planning}/refs/doctrine.md" ]]; then
    cp "${planning}/refs/doctrine.md" "${target}/principles/01-doctrine.md"
  fi

  # Layer drafts: outbox/worker-{1..5}/02-draft.md -> layers/{layer}.md.
  # Use parallel arrays for macOS bash 3.2 compatibility (no associative arrays).
  local layer_workers="worker-1 worker-2 worker-3 worker-4 worker-5"
  local layer_names="interface application domain infrastructure cross-cutting"
  local i=1 w layer_name src
  for w in $layer_workers; do
    layer_name=$(echo "$layer_names" | cut -d' ' -f$i)
    src="${planning}/outbox/${w}/02-draft.md"
    if [[ -f "$src" ]]; then
      cp "$src" "${target}/layers/${layer_name}.md"
    fi
    i=$((i + 1))
  done

  echo "Published into ${target}:"
  find "$target" -type f -name '*.md' | sort
  cmd_verify "${target}/layers"
}

case "${1:-}" in
  init)     shift; cmd_init "$@" ;;
  dispatch) shift; cmd_dispatch "$@" ;;
  spawn)    shift; cmd_spawn "$@" ;;
  verify)   shift; cmd_verify "$@" ;;
  publish)  shift; cmd_publish "$@" ;;
  -h|--help|"") usage ;;
  *) echo "Unknown sub-command: $1" >&2; usage ;;
esac

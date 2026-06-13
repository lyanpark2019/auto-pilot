#!/usr/bin/env bash
# Single source of truth for swarm engine/model ids + base branch.
# Sourced by start.sh, run-pm.sh, bench.sh. Bump model ids HERE only.
# SC2034 disabled: vars are consumed by sourcing scripts via jq --arg and
# direct ref after source; the linter cannot see cross-file usage.
# shellcheck disable=SC2034
SWARM_PM_CLAUDE_MODEL="claude-opus-4-8"
SWARM_CODEX_DEFAULT_MODEL="gpt-5.5"
# POSIX ERE for jq test() and bash [[ =~ ]]; keep in sync with SKILL.md routing table.
SWARM_CODEX_MODEL_RE='^(gpt-5|gpt-5\.5|o3)$'
SWARM_BASE_BRANCH="HEAD"   # worktree base ref; was inline literal in start.sh:87
swarm_pm_default_model() {  # $1=engine -> echoes default pm model
  case "${1:-claude}" in
    codex) printf '%s\n' "$SWARM_CODEX_DEFAULT_MODEL";;
    *)     printf '%s\n' "$SWARM_PM_CLAUDE_MODEL";;
  esac
}

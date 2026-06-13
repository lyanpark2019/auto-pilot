#!/usr/bin/env bash
# Unit-test the swarm-models.sh config lib.
# Sources the real lib — test exercises actual values, not reimplementations.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SWARM_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"

# Source real lib.
# shellcheck source=swarm/scripts/lib/swarm-models.sh
. "$SWARM_ROOT/scripts/lib/swarm-models.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# (1) SWARM_PM_CLAUDE_MODEL re-stale guard
# ---------------------------------------------------------------------------
[ "$SWARM_PM_CLAUDE_MODEL" = "claude-opus-4-8" ] \
  || fail "SWARM_PM_CLAUDE_MODEL is '$SWARM_PM_CLAUDE_MODEL', expected 'claude-opus-4-8'"

# ---------------------------------------------------------------------------
# (2) SWARM_CODEX_MODEL_RE matches valid ids and rejects stale ones
# ---------------------------------------------------------------------------
for good in "gpt-5" "gpt-5.5" "o3"; do
  [[ "$good" =~ $SWARM_CODEX_MODEL_RE ]] \
    || fail "SWARM_CODEX_MODEL_RE should match '$good'"
done
for bad in "gpt-4" "gpt-4o" "claude-opus-4-8" "gpt-5.6"; do
  [[ "$bad" =~ $SWARM_CODEX_MODEL_RE ]] \
    && fail "SWARM_CODEX_MODEL_RE should NOT match '$bad'" || true
done

# ---------------------------------------------------------------------------
# (3) GATE-EQUIVALENCE: same jq expression as start.sh
# ---------------------------------------------------------------------------
TMPDIR_TC="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TC"' EXIT

# 3a: claude engine + current model → accept (exit 0)
cat > "$TMPDIR_TC/cfg-accept.json" <<EOF
{"pm":{"engine":"claude","model":"$SWARM_PM_CLAUDE_MODEL"},"workers":[],"initial_goal":{"title":"t","success_criteria":["x"]}}
EOF
jq -e --arg cm "$SWARM_PM_CLAUDE_MODEL" --arg crx "$SWARM_CODEX_MODEL_RE" '
  if (.pm.engine // "claude") == "claude" then (.pm.model // $cm) == $cm
  else (.pm.model // "gpt-5.5") | test($crx) end
' "$TMPDIR_TC/cfg-accept.json" >/dev/null \
  || fail "gate-equivalence: current model should be ACCEPTED"

# 3b: claude engine + stale model → reject (nonzero)
cat > "$TMPDIR_TC/cfg-stale.json" <<EOF
{"pm":{"engine":"claude","model":"claude-opus-4-7"},"workers":[],"initial_goal":{"title":"t","success_criteria":["x"]}}
EOF
jq -e --arg cm "$SWARM_PM_CLAUDE_MODEL" --arg crx "$SWARM_CODEX_MODEL_RE" '
  if (.pm.engine // "claude") == "claude" then (.pm.model // $cm) == $cm
  else (.pm.model // "gpt-5.5") | test($crx) end
' "$TMPDIR_TC/cfg-stale.json" >/dev/null \
  && fail "gate-equivalence: stale 'claude-opus-4-7' should be REJECTED" || true

# ---------------------------------------------------------------------------
# (4) swarm_pm_default_model returns correct values
# ---------------------------------------------------------------------------
got_claude="$(swarm_pm_default_model claude)"
[ "$got_claude" = "claude-opus-4-8" ] \
  || fail "swarm_pm_default_model claude → '$got_claude', expected 'claude-opus-4-8'"

got_codex="$(swarm_pm_default_model codex)"
[ "$got_codex" = "gpt-5.5" ] \
  || fail "swarm_pm_default_model codex → '$got_codex', expected 'gpt-5.5'"

# Default (no arg) should also return claude model.
got_default="$(swarm_pm_default_model)"
[ "$got_default" = "claude-opus-4-8" ] \
  || fail "swarm_pm_default_model (no arg) → '$got_default', expected 'claude-opus-4-8'"

# ---------------------------------------------------------------------------
# (5) ABSENCE: no 'claude-opus-4-7' literals remain in swarm/scripts
# ---------------------------------------------------------------------------
if grep -RIl 'claude-opus-4-7' "$SWARM_ROOT/scripts"; then
  fail "stale 'claude-opus-4-7' literal found in swarm/scripts — see above"
fi

echo 'models-config tests passed'

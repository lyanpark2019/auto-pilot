#!/usr/bin/env bats
# Regression pins for load-bearing fenced snippets in auto-pilot/SKILL.md.
# Run: bats tests/

_skill_md() {
  printf '%s\n' "${BATS_TEST_DIRNAME}/../SKILL.md"
}

_section_between() {
  local start="$1" end="$2"
  awk -v start="$start" -v end="$end" '
    index($0, start) { in_section=1 }
    in_section { print }
    in_section && index($0, end) && !index($0, start) { exit }
  ' "$(_skill_md)"
}

_assert_contains() {
  local haystack="$1" needle="$2"
  [[ "$haystack" == *"$needle"* ]] || {
    printf 'missing expected snippet:\n%s\n' "$needle" >&2
    return 1
  }
}

@test "pre-flight step 7 pins hardened reviewer registry check" {
  local section
  section="$(_section_between '7. **Subagent registry presence check' '8. **Codex sandbox probe')"

  _assert_contains "$section" ': "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT unset — cannot locate plugin agents}"'
  _assert_contains "$section" 'for agent in auto-pilot-claude-reviewer auto-pilot-codex-reviewer; do'
  _assert_contains "$section" 'f="${CLAUDE_PLUGIN_ROOT}/agents/${agent}.md"'
  _assert_contains "$section" "sed -n '2,/^---$/p' \"\$f\" | grep -qx \"name: \${agent}\""
  _assert_contains "$section" 'echo "auto-pilot: hardened reviewer pair unavailable —${missing} (aborting; no legacy fallback)" >&2'
  _assert_contains "$section" 'exit 3'
}

@test "pre-flight step 8 pins codex sandbox help-text probe" {
  local section
  section="$(_section_between '8. **Codex sandbox probe' 'The hardened pair')"

  _assert_contains "$section" 'if codex exec --help 2>&1 | grep -q -- '\''--sandbox'\''; then'
  _assert_contains "$section" 'export AUTO_PILOT_CODEX_SANDBOX_AVAILABLE=1'
  _assert_contains "$section" 'echo "auto-pilot: codex lacks --sandbox; layer 4 deterrent disabled" >&2'
  _assert_contains "$section" 'export AUTO_PILOT_CODEX_SANDBOX_AVAILABLE=0'
}

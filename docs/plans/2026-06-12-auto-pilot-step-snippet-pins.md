# auto-pilot Step Snippet Pins Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add regression tests that pin auto-pilot `SKILL.md` pre-flight Step 7 / Step 8 fenced snippets.

**Architecture:** Add a skill-local Bats suite that reads `skills/auto-pilot/SKILL.md` and asserts narrow, load-bearing substrings inside the Step 7 and Step 8 fenced snippets. Wire the suite into CI and repo verification docs.

**Tech Stack:** Bats, Bash, GitHub Actions.

---

### Task 1: Add failing auto-pilot snippet-pin tests

**Files:**
- Create: `skills/auto-pilot/tests/skill-snippets.bats`
- Read: `skills/auto-pilot/SKILL.md`

**Step 1: Create the Bats test file**

Add helpers that locate `../SKILL.md` from `BATS_TEST_DIRNAME` and extract a bounded section between the Step 7/8 headings.

**Step 2: Pin Step 7 load-bearing lines**

Assert the Step 7 section contains:

```bash
: "${CLAUDE_PLUGIN_ROOT:?CLAUDE_PLUGIN_ROOT unset — cannot locate plugin agents}"
for agent in auto-pilot-claude-reviewer auto-pilot-codex-reviewer; do
f="${CLAUDE_PLUGIN_ROOT}/agents/${agent}.md"
sed -n '2,/^---$/p' "$f" | grep -qx "name: ${agent}"
exit 3
```

**Step 3: Pin Step 8 load-bearing lines**

Assert the Step 8 section contains:

```bash
codex exec --help 2>&1 | grep -q -- '--sandbox'
export AUTO_PILOT_CODEX_SANDBOX_AVAILABLE=1
export AUTO_PILOT_CODEX_SANDBOX_AVAILABLE=0
```

**Step 4: Run the new test to verify current behavior**

```bash
cd skills/auto-pilot && bats tests/
```

Expected: PASS if the current snippets still contain the pinned lines.

### Task 2: Wire the new suite into verification

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `CLAUDE.md`

**Step 1: Add CI step**

In the existing `bats` job, add a step:

```yaml
- name: bats (auto-pilot skill snippets)
  working-directory: skills/auto-pilot
  run: bats tests/
```

Also update the job name text from “adversarial-review-loop + setup-harness” to include auto-pilot.

**Step 2: Update repo verification docs**

In `CLAUDE.md`, update the Bats command block to include:

```bash
( cd skills/auto-pilot && bats tests/ )
```

### Task 3: Verify and commit

**Files:**
- Test: `skills/auto-pilot/tests/skill-snippets.bats`
- Test: `.github/workflows/ci.yml`
- Test: `CLAUDE.md`
- Commit: docs plan/design files

**Step 1: Run target suite**

```bash
cd skills/auto-pilot && bats tests/
```

Expected: all tests pass.

**Step 2: Run all Bats suites named in CLAUDE.md**

```bash
( cd skills/auto-pilot && bats tests/ )
( cd skills/adversarial-review-loop && bats tests/ )
( cd skills/setup-harness && bats tests/ )
```

Expected: all pass.

**Step 3: Check diff hygiene**

```bash
git diff --check
```

Expected: no whitespace errors.

**Step 4: Commit with trailers**

```bash
git add CLAUDE.md .github/workflows/ci.yml \
  docs/plans/2026-06-12-auto-pilot-step-snippet-pins-design.md \
  docs/plans/2026-06-12-auto-pilot-step-snippet-pins.md \
  skills/auto-pilot/tests/skill-snippets.bats
git commit -m "test: pin auto-pilot step snippets" \
  -m "Rejected: full markdown snapshot | too brittle for small snippet guard" \
  -m "Constraint: keep follow-up PR isolated from hook/runtime changes" \
  -m "Not-tested: full repo pytest/mypy/ruff suite" \
  -m "Confidence: high"
```

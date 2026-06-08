# Release State Consistency Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a tested invariant that release quality state matches the shipped `v0.8.7` plugin release.

**Architecture:** A repo-level test reads the plugin manifests and `.planning/quality/score-state.json` as tracked release evidence. The implementation updates only the state artifact so release status, CI run, tag, URL, and residual risks match the published release.

**Tech Stack:** Python stdlib `json`/`pathlib`, pytest, existing `.planning/quality` release artifacts.

---

### Task 1: Commit design and plan

**Files:**
- Create: `docs/plans/2026-06-08-release-state-consistency-design.md`
- Create: `docs/plans/2026-06-08-release-state-consistency.md`

**Step 1: Inspect git status**

Run: `git status --short`
Expected: only the two plan files are untracked.

**Step 2: Commit docs**

Run:
```bash
git add docs/plans/2026-06-08-release-state-consistency-design.md docs/plans/2026-06-08-release-state-consistency.md
git commit -m "docs: plan release state consistency"
```
Expected: commit succeeds.

### Task 2: Add failing release-state invariant test

**Files:**
- Create: `tests/test_release_state.py`

**Step 1: Write the failing test**

Create a pytest file that:
- loads `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`, and `.planning/quality/score-state.json`,
- asserts both manifest versions are `0.8.7`,
- asserts state `current_state == "RELEASED_V0_8_7"`,
- asserts release evidence fields for tag `v0.8.7`, commit `e3200cb2b730c9bca60b57ca0a92ccd3d3ddb8bb`, CI run `27138414829`, and release URL,
- asserts residual risks and decision do not contain pending/blocker language.

**Step 2: Run test to verify RED**

Run: `python3 -m pytest tests/test_release_state.py -q`
Expected: FAIL because current state still says `CI_FIX_PUSH_READY` or release-blocked text.

### Task 3: Update score-state evidence

**Files:**
- Modify: `.planning/quality/score-state.json`

**Step 1: Write minimal implementation**

Update fields only as needed:
- `current_state`: `RELEASED_V0_8_7`
- `head_sha`: full release commit SHA
- `mode`: released wording
- `scores_source`: include dual rescore and release evidence
- `measurement_log`: add PR/main/release CI and release URL entries
- `residual_risks`: remove hosted-CI/release-pending risks and replace with true residual risks
- `decision`: state that `v0.8.7` shipped
- add `release` object with tag, URL, commit, CI run, manifest version.

**Step 2: Run test to verify GREEN**

Run: `python3 -m pytest tests/test_release_state.py -q`
Expected: PASS.

### Task 4: Verify and commit implementation

**Files:**
- Create: `tests/test_release_state.py`
- Modify: `.planning/quality/score-state.json`

**Step 1: Run targeted and standard checks**

Run:
```bash
python3 -m pytest tests/test_release_state.py -q
python3 -m pytest tests/ -q
python3 -m mypy scripts/ hooks/
python3 -m ruff check scripts/ tests/ hooks/
```
Expected: all pass.

**Step 2: Commit**

Run:
```bash
git add tests/test_release_state.py .planning/quality/score-state.json
git commit -m "test: enforce release state consistency"
```
Expected: commit succeeds with verification evidence in commit trailers.

# Release State Invariant Generalization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generalize the release-state consistency test so manifest-derived invariants are reusable while `v0.8.7` evidence remains strict.

**Architecture:** Refactor `tests/test_release_state.py` around a helper that accepts already-loaded manifest/state dictionaries. The helper derives version, tag, and released-state expectations from manifest data; the concrete repository test still asserts current commit, CI run, and release URL evidence.

**Tech Stack:** Python stdlib `copy`, `json`, `pathlib`; pytest.

---

### Task 1: Commit design and plan

**Files:**
- Create: `docs/plans/2026-06-08-release-state-invariant-generalization-design.md`
- Create: `docs/plans/2026-06-08-release-state-invariant-generalization.md`

**Step 1: Inspect status**

Run: `git status --short`
Expected: only the two plan files are untracked.

**Step 2: Commit docs**

Run:
```bash
git add docs/plans/2026-06-08-release-state-invariant-generalization-design.md docs/plans/2026-06-08-release-state-invariant-generalization.md
git commit -m "docs: plan release state invariant generalization"
```
Expected: commit succeeds.

### Task 2: RED synthetic next-release test

**Files:**
- Modify: `tests/test_release_state.py`

**Step 1: Write failing test**

Add `test_release_state_invariant_derives_version_from_manifest()` that:
- deep-copies loaded current JSON data,
- changes plugin and marketplace versions to `0.8.8`,
- changes release object tag/plugin_version/marketplace_version to `v0.8.8`/`0.8.8`,
- changes `current_state` to `RELEASED_V0_8_8`,
- calls a wished-for helper `_assert_release_state_consistency(...)`.

**Step 2: Run RED**

Run: `python3 -m pytest tests/test_release_state.py -q`
Expected: FAIL with `NameError` or missing helper because the generalized helper does not exist yet.

### Task 3: GREEN helper refactor

**Files:**
- Modify: `tests/test_release_state.py`

**Step 1: Implement helper**

Add helpers:
- `_marketplace_plugin(marketplace)` returns the first plugin dict,
- `_released_state_for(version)` returns `RELEASED_V<major>_<minor>_<patch>`,
- `_assert_release_state_consistency(plugin, marketplace, state)` checks manifest-derived invariants and no current pending/blocker language.

Keep strict current evidence constants for commit, CI run, and release URL in `test_v087_release_state_matches_plugin_manifests()`.

**Step 2: Run GREEN**

Run: `python3 -m pytest tests/test_release_state.py -q`
Expected: PASS.

### Task 4: Verify and commit

**Files:**
- Modify: `tests/test_release_state.py`

**Step 1: Run verification**

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
git add tests/test_release_state.py
git commit -m "test: generalize release state invariant"
```
Expected: commit succeeds with trailers.

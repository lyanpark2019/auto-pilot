---
manual_edit: true
---

# v0.8.6 Quality Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship v0.8.6 with CI Node-runtime deprecation cleanup and a second vault mypy pilot file.

**Architecture:** Keep the patch release narrow: update hosted CI action majors, extend the strict mypy surface to `vault/sources/code.py`, and release without moving prior tags.

**Tech Stack:** GitHub Actions, mypy strict config, pytest regression tests, Claude plugin manifests.

---

### Task 1: CI action runtime cleanup

**Files:**
- Modify: `.github/workflows/ci.yml`
- Test: `tests/test_ci_workflow_vault_gates.py`

**Steps:**
1. Add a failing regression that rejects deprecated `actions/checkout@v4` and `actions/setup-python@v5` pins.
2. Run the regression and confirm RED.
3. Update the workflow to the latest Node 24 action majors.
4. Run the regression and ruff.

### Task 2: Second vault mypy pilot

**Files:**
- Modify: `mypy.ini`
- Modify: `vault/sources/code.py`
- Test: `tests/test_mypy_scope.py`

**Steps:**
1. Extend the mypy scope regression to require `vault/sources/code.py`.
2. Run the regression and single-file mypy and confirm RED.
3. Add the file to `mypy.ini` and fix the strict type error in `vault/sources/code.py`.
4. Run the regression and full mypy.

### Task 3: v0.8.6 release

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**Steps:**
1. Bump both plugin manifests from `0.8.5` to `0.8.6`.
2. Run full local gates.
3. Verify GitHub CLI active account is `lyanpark2019`.
4. Fast-forward merge to `main`, push, wait for CI green.
5. Create annotated tag/release `v0.8.6`.

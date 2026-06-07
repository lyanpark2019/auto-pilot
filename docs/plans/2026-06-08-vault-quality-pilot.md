---
type: plan
topic: vault mypy pilot and canvas quality batch
source_commit: 2f5bfee6685a969281bdf54816c347bee60309ee
manual_edit: true
---

# Vault Quality Pilot Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add one safe vault file to the strict mypy surface, refactor the longest vault canvas function, and reduce raw print-style diagnostics without changing exported canvas behavior.

**Architecture:** Use `vault/pipeline/canvas.py` as the pilot because it is both the current longest vault function and has only four standalone mypy errors. Keep public API stable: `emit_graph_canvas(vault, max_nodes)` still writes `<vault>/meta/graph-hub.canvas` or returns `None`. Add characterization tests before refactoring, then include this file in `mypy.ini` so CI enforces the pilot.

**Tech Stack:** Python 3, pytest, mypy strict, ruff, JSON Canvas fixtures.

---

## Task 1: Characterize canvas behavior

**Files:**
- Create: `vault/tests/test_canvas.py`

**Steps:**
1. Add a fixture that writes `graphify-out/graph.json` with nodes and duplicate edges.
2. Assert `emit_graph_canvas()` writes top-ranked text nodes and deduplicated edges.
3. Assert missing and invalid graphs return `None` and do not create `meta/graph-hub.canvas`.
4. Run `cd vault && python3 -m pytest tests/test_canvas.py -q`.

## Task 2: Add strict mypy pilot gate

**Files:**
- Modify: `mypy.ini`
- Test: `tests/test_mypy_scope.py` or existing CI config test if appropriate.

**Steps:**
1. Add a regression test that requires `vault/pipeline/canvas.py` to be listed in mypy scope.
2. Confirm RED before editing `mypy.ini`.
3. Add `vault/pipeline/canvas.py` to `mypy.ini` `files`.
4. Run `python3 -m mypy vault/pipeline/canvas.py` and expect current RED until Task 3 fixes types.

## Task 3: Refactor and type `vault/pipeline/canvas.py`

**Files:**
- Modify: `vault/pipeline/canvas.py`

**Steps:**
1. Extract helpers for graph loading, degree ranking, canvas node building, and canvas edge building.
2. Replace raw diagnostic `print()` calls with small stdout/stderr writer helpers so CLI output remains stable while print-call count drops.
3. Add typed aliases/NamedTuple so strict mypy accepts the file.
4. Run:
   - `python3 -m mypy vault/pipeline/canvas.py`
   - `cd vault && python3 -m pytest tests/test_canvas.py tests/test_fix_verify_export.py -q`

## Task 4: Verify full affected surface

**Commands:**
- `python3 -m mypy`
- `python3 -m ruff check scripts/ tests/ hooks/ vault/`
- `cd vault && python3 -m pytest tests/ -q`
- `python3 -m pytest tests/ -q`
- `bash scripts/quality/check-module-size.sh`
- `python3 scripts/docs/check_doc_reference_integrity.py`

## Task 5: Commit, merge, push, and confirm CI

**Steps:**
1. Commit the plan separately.
2. Commit implementation with verification trailers.
3. Merge `quality/vault-pilot` back to `main` after local verification.
4. Push and confirm GitHub CI.

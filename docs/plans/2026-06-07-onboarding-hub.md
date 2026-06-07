---
type: plan
topic: graphify-backed AI / Developer onboarding hub
source_commit: fcebef1dce49d8cfe4d854f65dd9406986629f12
manual_edit: true
---

# AI / Developer Onboarding Hub Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a graphify-backed onboarding entry point so new developers and AI agents can understand auto-pilot's architecture and maintain it safely.

**Architecture:** Do not create a new skill or agent. The existing `doc-management` skill owns docs freshness and onboarding-hub rules; repo docs provide the concrete auto-pilot hub. Graphify remains the source for current code structure (`What`), while existing architecture/ADR/history docs preserve rationale (`Why`).

**Tech Stack:** Markdown docs, graphify CLI (`update`, `query`, `explain`, `path`, `affected`, `extract`), existing doc integrity checker, pytest characterization tests for docs routing.

---

## Additional Validation Findings

- Shared workflow source: `/Users/lyan/Documents/Knowledge/wiki/ai/workflows/graphify-docs-drift-refresh.md`.
- The workflow's What/Why split, Case A/B triage, and onboarding-hub output are adopted.
- Stale workflow details are corrected in repo docs: current Graphify CLI does not expose `graphify export html/wiki/obsidian`; use `graphify update . --force` for code graph refresh and `graphify extract . --mode deep` for full semantic rebuild.
- Current auto-pilot graph source of truth is repo-local `graphify-out/graph.json`, not `/Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot/_graph/graph.json`.
- `graphify-out/GRAPH_REPORT.md` was stale at commit `15318f76`; `graphify update . --force` rebuilt it at `ed4f8829` with 4,846 nodes and 7,073 edges.

## Task 1: Add docs routing tests

**Files:**
- Create: `tests/test_onboarding_docs.py`

**Steps:**
1. Add tests requiring `docs/README.md`, `docs/onboarding/README.md`, and the reusable doc-management onboarding reference.
2. Assert README routes developers and AI agents to the onboarding hub.
3. Assert onboarding docs mention graphify freshness commands and What/Why discipline.
4. Run `python3 -m pytest tests/test_onboarding_docs.py -q` and confirm RED.

## Task 2: Add repo docs entry points

**Files:**
- Create: `docs/README.md`
- Create: `docs/onboarding/README.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Steps:**
1. Write `docs/README.md` as the docs map and source-of-truth order.
2. Write `docs/onboarding/README.md` as the AI/developer start page with architecture map, task routing, graphify commands, and verification checklist.
3. Add short pointers from root `README.md` and `CLAUDE.md`.
4. Re-run `python3 -m pytest tests/test_onboarding_docs.py -q` and confirm GREEN.

## Task 3: Add reusable doc-management reference

**Files:**
- Create: `skills/doc-management/references/onboarding-hub.md`
- Modify: `skills/doc-management/SKILL.md`

**Steps:**
1. Distill the vault workflow into a reusable reference.
2. Correct current Graphify CLI command names.
3. Update `doc-management` SKILL.md to cite the reference and name onboarding hubs as a required REBUILD/MAINTAIN output when docs are being structured.
4. Run `python3 -m pytest tests/test_onboarding_docs.py -q`.

## Task 4: Verify docs and quality gates

**Commands:**
- `python3 scripts/docs/check_doc_reference_integrity.py`
- `python3 -m pytest tests/test_onboarding_docs.py tests/test_doc_reference_integrity.py -q`
- `python3 -m ruff check tests/test_onboarding_docs.py`
- `git diff --check`
- If time permits: `python3 scripts/graphify_vault_loop.py --vault /Users/lyan/Documents/Knowledge/wiki/projects/auto-pilot --compact --max-iterations 1`

## Task 5: Commit and merge

**Steps:**
1. Commit docs/tests with structured trailers.
2. Merge back to main after local checks.
3. Push and confirm CI.

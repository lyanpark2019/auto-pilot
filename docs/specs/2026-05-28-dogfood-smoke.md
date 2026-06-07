---
type: spec
topic: dogfood-smoke
source_commit: f726a9fa218eb29e2a01d54db4b94c0a1aaecb14
manual_edit: true
---

# Dogfood Smoke — 2-phase

**Date**: 2026-05-28
**Status**: gate fixture (used as acceptance harness for PR1+PR2 Tier 1 and PR3 Tier 2; spec distilled into `docs/architecture.md` §Contract layer/Worktree lifecycle/Reviewer sandbox)
**Scope**: Minimal 2-phase spec used as the acceptance harness for PR1+PR2 (Tier 1) and PR3 (Tier 2). Designed to be cheap, deterministic, and stable as the plugin evolves.

## Why

PR1–PR3 added contract layer, worktree lifecycle, and reviewer sandbox. The acceptance criteria in those PRs reference a smoke spec to verify the loop end-to-end with real subagent dispatch. This file is that spec — kept inside the plugin repo so `auto-pilot start --spec docs/specs/2026-05-28-dogfood-smoke.md` is always available.

## Acceptance per tier

| Tier | Reviewer mode | Artifact checks |
|---|---|---|
| 1 | `AUTO_PILOT_DISABLE_NEW_REVIEWERS=1` (general-purpose fallback) | 2 phases done, worktrees reaped, contracts schema-valid + signed, trailer chain present |
| 2 | Full PR3 reviewer sandbox | Tier 1 PLUS `review.json` schema-valid, `done.marker` + `exit-code.txt` per role, no `sandbox-violations.jsonl` entries |

## Phase 1 — Add no-op helper

**Goal**: PM dispatches a single worker, worker adds one pure function with type hint and one line of docstring.

**Scope files**: `scripts/_dogfood_noop.py` (new)

**Acceptance**:
- `scripts/_dogfood_noop.py` exists.
- Defines `def dogfood_identity(x: int) -> int:` returning `x`.
- mypy clean: `mypy scripts/_dogfood_noop.py`.
- ruff clean: `ruff check scripts/_dogfood_noop.py`.
- Single commit, single trailer block (`auto-pilot-iter`, `auto-pilot-phase: 1`, `auto-pilot-contract`, `auto-pilot-idempotency`).

**Verify cmd**: `python3 -c "from scripts._dogfood_noop import dogfood_identity; assert dogfood_identity(7) == 7"`

## Phase 2 — Add test

**Goal**: PM dispatches a single worker, worker adds one pytest test for the function added in Phase 1.

**Scope files**: `tests/test_dogfood_noop.py` (new)

**Acceptance**:
- `tests/test_dogfood_noop.py` exists.
- Contains at least one test calling `dogfood_identity` and asserting the result.
- `pytest tests/test_dogfood_noop.py` passes.
- Single commit with trailer block (`auto-pilot-phase: 2`).

**Verify cmd**: `pytest -q tests/test_dogfood_noop.py`

## Non-goals

- No refactoring, no dependencies added, no infrastructure changes.
- No long-running reviewers — both phases should approve in round 1.
- No multi-commit workers — each phase produces exactly one commit (worktree-lifecycle invariant).

## Cleanup

After a successful run, remove `scripts/_dogfood_noop.py` and `tests/test_dogfood_noop.py` before the next dogfood pass to keep the workspace clean. Tier scripts handle this automatically.

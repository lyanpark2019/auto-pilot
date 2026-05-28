# Deferred Cleanup — Plan

**Date**: 2026-05-29
**Branch**: `deferred-cleanup`
**Scope**: 4 items deferred from PM↔subagent contract hardening spec (`docs/specs/2026-05-28-pm-subagent-contract-hardening-design.md` § Out of scope).
**Packaging**: single PR.

## Items

### 1. `state.json` file lock

**Problem**: `_state.load_state` / `save_state` are unlocked. PM main session + headless driver + orchestrator CLI can race on the same file (`STATE_DIR/state.json`). Even single-writer assumption breaks when `orchestrator.py phase-start` runs while PM session is mid-update.

**Fix**: Reuse `_contract._atomic_write_text` + `write_lock`/`read_lock` against `STATE_DIR/state.lock`. `load_state` holds shared lock; `save_state` holds exclusive lock. Cross-platform fsync already handled by `_contract._fsync_*`.

**Touched**: `scripts/_state.py`. New file `tests/test_state_lock.py`.

**Acceptance**:
- 10 concurrent `save_state` writers via subprocess: no torn JSON, last-writer-wins.
- Reader during writer holds: reader sees pre-write or post-write, never partial.
- Lock file at `.planning/auto-pilot/state.lock`, not committed.

### 2. Spec-parser robustness (`_count_phases`)

**Problem**: `_count_phases` does naïve `startswith("## Phase ")` / `# Phase`. Counts:
- `## Phase` inside fenced code blocks (false positive).
- `### Phase` ignored (some specs nest).
- Indented headings ignored or counted depending on `strip()` (current: stripped, so indented are counted — may be wrong if inside list).

**Fix**: Track fenced code-block state (toggled by lines starting with ```` ``` ````). Count only lines matching `^#{1,3} Phase\b` outside fences. Documented invariant: spec author owns top-level phase headings, never embed `# Phase N` in fenced examples without comment.

**Touched**: `scripts/orchestrator.py`. Extended tests in `tests/test_orchestrator.py`.

**Acceptance**:
- Code-fenced `## Phase X` → ignored.
- `### Phase X` → counted.
- 0 phase headings → still floors at 1.
- Existing `sample_spec` fixture (3 phases) → still returns 3.

### 3. Headless cost cap + stash safety

**Problem**:
- `headless-loop.py` spawns `claude -p --dangerously-skip-permissions` with no upper-bound on cost/iterations. Bug-trigger fork-bomb risk.
- Used to `git reset --hard pre_head` on failure; PR2 removed that, but on `rc==124` (timeout) the iter is still abandoned without saving any work-in-progress for inspection.

**Fix**:
1. Add `--max-cost-usd` (default 50.0) and `--max-tokens` (default 50_000_000) to `headless-loop.py`. Parse `claude -p --output-format=json` totals from each session log line; accumulate in `state.json.cost_usd` / `state.json.tokens`. Before each iter, abort with status `cost-cap` if cap exceeded.
2. Add `--max-concurrent-claude` (default 4) cap. Before spawn: `pgrep -c '^claude$'` >= cap → wait/abort. Belt-and-suspenders for fork-bomb.
3. On any iter abandon (timeout or status=failed), `git stash push -u -m "auto-pilot-iter-{n}-abandoned"` ON THE WORKTREE/MAIN only if dirty. Tag is recoverable; no destructive reset. Note: existing PR2 logic already removed the destructive reset for $ROOT; this adds the stash for the rare case where main is dirty after a failed apply.

**Touched**: `scripts/headless-loop.py`, `scripts/_state.py` (new `cost_usd`/`tokens` fields), `scripts/_config.py` (new defaults). New tests in `tests/test_headless_loop.py`.

**Acceptance**:
- Cap-hit: state.json cost_usd > cap → next iter returns `cost-cap`, no claude spawn.
- pgrep-cap: 4 mocked `claude` pids present → spawn refused.
- Stash invoked on dirty $ROOT post-fail; not invoked when clean. Stash entry survives the iter.

### 4. Dogfood smoke spec + Tier 1/2 gates

**Problem**: PR3 spec § Dogfooding gate references `docs/specs/2026-05-28-dogfood-smoke.md`; file not written.

**Fix**:
1. `docs/specs/2026-05-28-dogfood-smoke.md` — minimal 2-phase spec. Phase 1: add `scripts/_dogfood_noop.py` with one pure fn. Phase 2: add `tests/test_dogfood_noop.py`. Acceptance per phase mirrors PR3 § Tier 2 criteria. Designed so a single `/auto-pilot start` run produces verifiable artifacts.
2. `scripts/dogfood_tier1.sh` — runs the spec with `AUTO_PILOT_DISABLE_NEW_REVIEWERS=1`. Asserts: 2 phases completed, all worktrees reaped, all contracts schema-valid + signed, trailer chain in `git log`.
3. `scripts/dogfood_tier2.sh` — runs the spec with full reviewer sandbox. Asserts Tier 1 criteria PLUS no `sandbox-violations.jsonl` entries, all `review.json` valid, intentional-violation fixture triggers exit 2.

Note: Tier scripts are runnable acceptance harnesses for humans; the bundled PR does NOT run them in CI (would require an interactive Claude Code session). CI only validates that the scripts parse, smoke-spec parses, and the gate-check helpers in Python work standalone.

**Touched**: `docs/specs/2026-05-28-dogfood-smoke.md`, `scripts/dogfood_tier1.sh`, `scripts/dogfood_tier2.sh`, `scripts/_dogfood_gate.py` (Python helper for assertions). Tests in `tests/test_dogfood_gate.py`.

**Acceptance**:
- Smoke spec is parseable by `_count_phases` → returns 2.
- Tier scripts have `set -euo pipefail` + executable bit.
- Gate helper `_dogfood_gate.assert_tier1(contracts_dir)` raises on missing artifact, passes on synthetic fixture.

## Risk register

| Risk | Mitigation |
|---|---|
| `state.lock` race with `_contract.write_lock` (different lock files) | Independent locks; no cross-contention. `state.lock` lives alongside `state.json`. |
| Token/cost parsing fragile if `claude -p` JSON shape changes | Best-effort parse, default to 0 on missing keys. Cost cap fails-open (warn) not fails-closed. |
| `pgrep` not portable (Linux vs macOS difference in `^claude$` match) | Use `pgrep -x claude` (portable); fallback to no-op if pgrep absent. |
| Stash push during concurrent worker = race | Only invoked from outer driver (single-writer); worktree dirty checks elsewhere. |
| Smoke spec stale as harness evolves | Spec scope intentionally minimal (no-op fn + test) — stays valid as long as Python syntax holds. |

## Test surface

- `test_state_lock.py`: 4 cases (atomic, concurrent, reader-during-writer, lock file location).
- `test_orchestrator.py` (additions): 3 cases (code-fenced phases, `### Phase` depth, no-phase fallback unchanged).
- `test_headless_loop.py` (additions): 3 cases (cost-cap state, pgrep-cap mock, stash-on-fail mock).
- `test_dogfood_gate.py`: 4 cases (tier1 pass, tier1 missing-trailer fail, tier2 pass with no violations, tier2 fail on synthetic violation).

Existing 159 tests must remain green.

## Out of scope

- Composition-root env-var self-bypass (trust model, separate spec).
- `pre-bash-guard.sh` SSL regex over-eager (hook tuning).
- `post-deploy-verify` per-Bash latency (hook tuning).
- CLAUDE.md "SessionStart re-reads" docs fix (drift-free now since we run a fresh session per iter — no docs fix required).

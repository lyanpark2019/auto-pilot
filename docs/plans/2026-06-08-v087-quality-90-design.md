---
type: design
topic: v0.8.7 quality 90 release
source_commit: ef8ba97743f7b55d3277829b9650816691162247
manual_edit: true
---

# v0.8.7 Quality 90 Release Design

## Goal

Ship a balanced multi-wave quality release that moves auto-pilot from the v0.8.6 conservative score of **84.40** to **90+**, with dual adversarial rescore, local full gates, hosted CI green, release publication, and plugin update.

The release must not move existing tags (`v0.8.4`, `v0.8.5`, `v0.8.6`). All GitHub release operations must use the `lyanpark2019` account.

## Baseline

Current release state:

- Head: `ef8ba97` (`v0.8.6`)
- Weighted score: `84.40`
- Root tests: `595 passed`
- Vault tests: `91 passed`
- Coverage: `80.06%`
- mypy strict: clean across `36 source files`
- ruff: clean across `scripts/ tests/ hooks/ vault/`
- Hosted CI: green (`27098380367`)

Current debt metrics:

- broad exceptions: `30`
- raw print calls: `168`
- long functions over 40 lines: `34`
- strict vault mypy pilots: `vault/pipeline/canvas.py`, `vault/sources/code.py`

## Approach

Use a **Balanced, 5-worker, hybrid score-max, multi-wave** plan.

The PM session freezes metrics, dispatches workers by file ownership plus score dimension, merges work in small batches, reruns local full gates, and rescans metrics after each wave. If Wave 2 reaches 90+, run dual adversarial rescore, reconcile conservatively, update score-state, then release `v0.8.7`.

Implementation remains behavior-preserving unless a test explicitly proves the intended behavior change.

## Worker Model

### Worker 1 — Type Scope

Purpose: expand strict mypy coverage for `vault/` from 2 pilot files to at least 8 files.

Initial candidates:

- `vault/sources/_adapter.py`
- `vault/sources/docs.py`
- `vault/pipeline/scan_code.py`
- `vault/scripts/lockfile.py`
- `vault/scripts/dashboard_data.py`
- `vault/pipeline/drift.py`

Rules:

- Do not add all `vault/` to mypy at once.
- Measure each candidate with single-file mypy first.
- Add only low-to-medium surface files.
- Update `tests/test_mypy_scope.py` for each accepted pilot.

### Worker 2 — Error Handling

Purpose: reduce broad exception handlers from `30` to `<=15` without weakening isolation behavior.

Priority files:

- `vault/scripts/lockfile.py`
- `vault/pipeline/scan_code.py`
- `vault/scripts/selftest.py`
- `scripts/graphify_vault_loop.py`
- `hooks/codex-conductor-guard.py`

Rules:

- Narrow JSON/YAML parsing to parser-specific exceptions.
- Narrow filesystem paths to `OSError` or `FileNotFoundError` as appropriate.
- Narrow subprocess paths to `subprocess.SubprocessError`, `TimeoutExpired`, or `CalledProcessError`.
- Preserve intentional per-destination isolation only when a regression test proves it.
- Unexpected parser/runtime exceptions must not be swallowed.

### Worker 3 — Logging and Output

Purpose: reduce raw print calls from `168` to `<=80` while preserving CLI stdout/stderr contracts.

Priority files:

- `vault/scripts/*.py`
- `vault/pipeline/*.py`
- `scripts/graphify_vault_loop.py`

Rules:

- Library/helper layers should not call raw `print()`.
- User-facing stdout goes through `_emit()` or equivalent.
- Warnings/errors go through `_warn()` or equivalent.
- Low-level stream writing goes through `_write_line()`.
- Error output should include `error_type=` when meaningful.
- Characterization tests must protect CLI-facing output before refactors.

### Worker 4 — Structure

Purpose: reduce long functions from `34` to `<=20` and extract top offenders without changing behavior.

Priority files:

- `vault/scripts/restructure_phases/phase06_vault_build.py:run` (`80` lines)
- `hooks/guard-destructive.py:main` (`74` lines)
- `vault/scripts/restructure_loop.py:main` (`72` lines)
- `scripts/_dispatch.py:prepare_subagent_ticket` (`69` lines, defer if too risky)
- `scripts/orchestrator.py:cmd_phase_start` (`66` lines)

Rules:

- Add characterization tests first.
- Extract private helpers only.
- Preserve hook stdin JSON contracts and exit-code semantics.
- Avoid public API expansion.
- Defer core modules if tests are not strong enough.

### Worker 5 — Test, CI, Score, Release

Purpose: keep the quality lift measurable and releasable.

Responsibilities:

- Add/maintain metric scanner evidence.
- Improve coverage where it materially supports scoring, especially `scripts/headless-loop.py` or `scripts/graphify_vault_loop.py` if feasible.
- Keep CI/local gates aligned.
- Prepare dual rescore artifacts.
- Prepare release notes and manifest bump after score is validated.

Rules:

- Release commit happens only after all workers merge and local full gates pass.
- Score-state updates must include file:line evidence for dimension increases.
- Use conservative reconciliation when Claude and Codex scores differ.

## Wave Targets

### Wave 1

Wave 1 reduces the largest debt but does not claim 90.

Targets:

- broad exceptions: `30 -> <=20`
- raw print calls: `168 -> <=110`
- long functions: `34 -> <=25`
- strict vault mypy pilots: `2 -> >=5`
- coverage: `80.06% -> >=81%` or materially better weak-path coverage

Expected score: `87.0-88.2`.

### Wave 2

Wave 2 crosses the 90 threshold.

Targets:

- broad exceptions: `<=15`
- raw print calls: `<=80`
- long functions: `<=20`
- strict vault mypy pilots: `>=8`
- test evidence improved enough to justify Test Quality `90`
- documentation updated if behavior or operator workflows change

Expected score: `90.0-91.0`.

## Gates

Every wave must pass:

```bash
python3 -m pytest tests/ -q
( cd vault && python3 -m pytest tests/ -q )
python3 -m mypy
python3 -m ruff check scripts/ tests/ hooks/ vault/
bash scripts/quality/check-module-size.sh
python3 scripts/docs/check_doc_reference_integrity.py
python3 skills/doc-management/scripts/check_design_doc_freshness.py docs/
```

Metric scan must report:

- broad exception count
- raw print count
- long function count
- mypy scope list
- coverage summary

No green gates means no score lift.

## Stop and Pivot Rules

Stop and ask the user if:

- A worker changes hook behavior without tests.
- CI remains red after one targeted fix attempt.
- broad exception reduction would alter recoverability semantics.
- print removal changes documented CLI output.
- mypy expansion exposes broad architectural debt.
- Wave 2 remains below 89 after honest rescore.

If Wave 1 succeeds but Wave 2 becomes risky, ship `v0.8.7` as an 87-88 quality release and reserve 90 for `v0.8.8`.

## Rescore and Release Protocol

After Wave 2 gates pass:

1. PM computes metric-based conservative score.
2. Codex produces independent 13-dimension JSON rescore.
3. Claude produces cold rescore report.
4. PM reconciles using the lower score when disagreement is meaningful.
5. Update `.planning/quality/score-state.json` with file:line evidence.
6. If final weighted score is `>=90`, bump plugin manifests to `0.8.7`.
7. Verify `gh auth status` active account is `lyanpark2019`.
8. Push `main`, wait for hosted CI green, create annotated tag and GitHub release.
9. Run `claude plugin update auto-pilot@auto-pilot-marketplace` and report restart requirement.

## Expected Artifacts

- `docs/plans/2026-06-08-v087-quality-90-design.md`
- implementation plan under `docs/plans/`
- worker contracts under `.planning/quality/contracts/`
- before/after metric snapshots
- Codex rescore JSON
- Claude rescore report
- updated `.planning/quality/score-state.json`
- `v0.8.7` release notes

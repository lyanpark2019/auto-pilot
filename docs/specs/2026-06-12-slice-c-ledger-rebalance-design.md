---
type: spec
topic: slice-c-ledger-rebalance
manual_edit: true
---

# Slice C — Routing Ledger Auto-append + PM Rebalance Evaluation

**Date**: 2026-06-12
**Status**: approved design — input to implementation plan
**Scope**: Slice C only. Consumes Slice A+B telemetry.
**Cites**: `docs/specs/2026-06-12-model-routing-enforcement-design.md`

## Problem

The routing rules in `skills/auto-pilot/references/model-routing.md` "Routing ledger & PM rebalance" section are prose with no enforcement:

1. Ledger append is manual and forgettable — nothing calls it at phase-end.
2. Rebalance evaluation never runs — no command exists to compute proposals.
3. The `p0_escaped` outcome field (promote-real-p0 rule) is undeclared in the schema.

## Design

### §1 Module split: `scripts/_ledger.py` + `scripts/_rebalance.py`

The original single-module design was split (F10) so both files stay under 500 lines and the IO/side-effect layer is separate from the pure rule engine:

**`scripts/_ledger.py`** — IO, schema validation, record derivation. Re-exports `evaluate_rebalance` from `_rebalance.py` for backward-compat callers. Public API:

- `LedgerError(Exception)` — malformed YAML or schema violation.
- `load_ledger(path: Path) -> dict` — missing file → fresh skeleton; malformed → LedgerError.
- `validate_ledger(data) -> None` — jsonschema Draft202012Validator against `schemas/routing-ledger.schema.json:1`; lazy-load pattern from `scripts/_ledger.py:58` (`_ledger_validator()` / `_LEDGER_VALIDATOR` global at line 39).
- `save_ledger(path, data) -> None` — validate then `_contract.atomic_write_text` with `yaml.safe_dump`.
- `build_record_from_round_dirs(contract_dir, round_dirs) -> dict` — derive one ledger record from evidence artifacts. `round_dirs` must be ALL round-* dirs for the contract (F1/F3), sorted by name. Auto-derives `p0_escaped=True` when any review.json across all rounds carries a P0 finding (F4). contract.json is read from the final round dir (`round_dirs[-1]`), NOT from the `contract-K/` parent. The `contract-K/` parent is used only for globbing all round-* subdirs. `worker_model` is the correct contract schema field; `model`, `role`, and `task_class` are NOT in the contract schema — `role` and `task_class` are always defaulted to `worker-primary`/`feature-multi-file` with a `notes` annotation. Approximations (documented in docstring + `notes`): `rejects_real` counts REJECT verdicts carrying ≥1 P0/P1 finding (P2-only REJECT counts as `rejects_false`); `gates_first_try` from `outputs/worker/status.json` if available, else inferred from `review_rounds == 1`.
- `append_phase_records(project_root, contracts_root) -> int` — orchestration glue: discovers finished contracts via `scripts/_evidence.py:150`, collects ALL round-* dirs per contract (F1/F3), builds records, skips already-present task_ids (idempotent), saves to `<project_root>/.claude/routing/ledger.yaml`, returns count appended.

**`scripts/_rebalance.py`** — pure rule engine. Zero IO; operates on plain dicts only. Public API:

- `normalize_model_token(token, ladder, config=None) -> str` — F2: maps short agent-tool tokens (sonnet→sonnet-4.6-1m, opus→opus-4.8, haiku→haiku-4.5) via `_routing.model_rank` rank→ladder[rank]. Tokens already in ladder pass through unchanged. Unknown tokens (gpt-5.5) also pass through unchanged.
- `evaluate_rebalance(ledger, ladder, config=None) -> list[dict]` — pure function; returns proposed `rebalance_log` entries (never written unless `--apply`). Four rules: `promote-2x-gate-fail`, `promote-real-p0`, `trial-demotion-3x-clean`, `revert-trial`.
  - F2: normalises model tokens before ladder lookup.
  - F5: filters to records newer than the group's latest rebalance entry (re-run idempotency).
  - F6: revert-trial only fires on records newer than the trial-demotion entry (temporal guard).
  - F7: uses enumerate indices, never `list.index()` (by-value equality bug).
  - F8: at most one promote rule fires per group per call (double-promote prevention).
  - F9: assignments keyed by composite `"<role>/<task_class>"` when `--apply` writes back.
  - F-D: revert-trial takes precedence over promote rules — when revert-trial fires for a group, promote rules are suppressed for that group in the same pass.
  - F-E: all ts comparisons use `datetime.fromisoformat`-parsed aware datetimes normalized to UTC (handles `+HH:MM` offsets, fractional seconds, `Z` vs `+00:00` equality).

### §2 Schema touch — `schemas/routing-ledger.schema.json`

- Added OPTIONAL `p0_escaped: {"type": "boolean"}` to `outcome.properties`. F12: `$schema` updated from draft-07 to `https://json-schema.org/draft/2020-12/schema` to match the `Draft202012Validator` used in code. `additionalProperties: false` stays. Additive only.

### §3 `scripts/_routing.py` — `tier_ladder()` + `model_rank()`

`tier_ladder(config)` reads the `tier_ladder` list from `model-routing.yaml` (`scripts/_routing.py:102`). `model_rank(token, config)` reads `agent_model_rank` section — used by `_rebalance.normalize_model_token` for F2.

### §4 `scripts/orchestrator.py` wiring

- `cmd_ledger_append` → calls `_ledger.append_phase_records`. F-C: when `--project-root` is supplied, `cmd_ledger_append` derives `contracts_root` from `project_root / STATE_DIR.relative_to(cwd) / "contracts"` rather than the cwd-relative `STATE_DIR / "contracts"`, so callers that pass a non-cwd project root find contracts in the correct location.
- `cmd_ledger_rebalance` → loads ledger + validates (F11) + reads ladder, prints proposals as table; `--apply` writes composite-key assignments (F9) + saves.
- `cmd_phase_end` — after evidence gate, before `_close_phase`: wrapped `try/except` call to `_ledger.append_phase_records`; on failure `_warn()` + continue. All heavy logic lives in `_ledger.py` and `_rebalance.py`.

### §5 Composite-key convention (F9)

`assignments` keys written by `ledger-rebalance --apply` use the form `"<role>/<task_class>"` (e.g., `"worker-primary/feature-multi-file"`). Hand-authored assignments using plain role keys remain valid — `_current_model_for_group` checks the composite key first, then the plain role key as fallback. The JSON schema's `additionalProperties` on the assignments object allows arbitrary string keys.

### §5 Docs (same change)

- `skills/auto-pilot/references/model-routing.md` ledger section: "Enforced:" bullet.
- `skills/auto-pilot/SKILL.md` phase-end flow: ledger note.
- `agents/pm-orchestrator.md` state-checkpoint rule: one-line ledger mention.

## Error handling

- `load_ledger`: missing file → skeleton (silent recovery); malformed YAML → LedgerError.
- `validate_ledger`: schema violation → LedgerError.
- `save_ledger`: IO failure propagates as OSError (caller wraps in phase-end try/except).
- `evaluate_rebalance`: unknown model → skip group silently. Ladder bounds enforced.
- Phase-end wiring: any exception from `append_phase_records` → one-line `_warn()`, return continues. Ledger is telemetry, never a gate.

## Testing

`tests/test_ledger.py` covers: load-missing→skeleton; malformed→LedgerError; validate accepts seed + rejects bad records; save round-trips; build_record derivation (all rounds, p0_escaped auto-derive, multi-round review_rounds count); evaluate_rebalance all four rules fire + near-miss negatives; normalize_model_token short-to-canonical mapping (F2 real ladder integration); re-run after --apply (F5 idempotency); revert-trial temporal guard (F6 near-miss); composite-key assignments (F9); schema-invalid dry-run exits nonzero (F11); append cross-iteration task_id (F1); phase-end ledger failure does not block. See `tests/test_routing.py` for style mirror.

## Residual risks

- `rejects_real` is an approximation derived from review verdict + finding severity. A REJECT carrying only P2 findings is classified as `rejects_false`. A reviewer who files a P0 without a REJECT verdict (finding noted inline) would not increment `rejects_real`. Documented in docstring; the derivation rule is honest.
- `gates_first_try` inference from `review_rounds == 1` is lossy when the worker reran verify internally before the first review. Documented in `notes` when inferred.
- Ledger is per-project (project-relative path `<project>/.claude/routing/ledger.yaml`); the `append_phase_records` function takes `project_root` as an explicit argument — callers must pass the correct root, not assume cwd.
- Archive rotation (keep latest 50 records, 90-day window) is specified in `model-routing.md` but deferred to v2; v1 appends without archiving.
- Auto-derived records collapse to group `("worker-primary","feature-multi-file")` because the contract schema (`schemas/contract.schema.json`, `additionalProperties:false`) carries no `role` or `task_class` fields — so the rebalance engine's per-`(role,task_class)` grouping is only meaningful for HAND-AUTHORED ledger records (like the ai-content-hub seed). Records appended via `append_phase_records` all land in the same default group; per-task_class precision via composite keys is best-effort telemetry on one merged stream. This is a v1 limitation; role+task_class fields in the contract schema would fix it in v2.

## Non-goals

- Archive/rotation logic (v2).
- Role×task dispatch resolver (not needed; Slice A+B left this intentionally absent).
- Codex model assignments (ladder maps Claude tiers only; gpt-5.5 skipped in rebalance).
- Automatic `--apply` of rebalance proposals (PM applies manually after judgment).

## Disposal

Ship → distill wiring into `docs/architecture.md`; delete this spec. Update `model-routing.md` if wiring changes.

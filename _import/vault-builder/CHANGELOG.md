# Changelog

## [0.3.0] — 2026-05-14 (PM dispatch wiring + dispatch board)

### Added
- `pipeline/dispatch.py` — `DispatchBoard` (per-project ticket lifecycle: pending → dispatched → delivered → verified/rejected → reissue or escalate, 3-strike cap, persistent state in `.vault-builder/dispatch-state.json`)
- `agents/pm-orchestrator.md` — Drift-fix mode section with full workflow (load-plan → parallel dispatch → deliver → verify → reissue → final rubric check)
- `commands/vault-build.md` — Explicit PM Agent invocation step between Phase 3 (fix plan) and Phase 4 (verify)
- `tests/test_dispatch.py` — 6 cases (load/dispatch/deliver/verify/reissue/3-strike/persistence/summary)

### Status
- Tests: 59 passing (was 53)
- Selftest: 10/10 PASS
- ga4-collector: 30 ticket board loaded, ready for PM dispatch

## [0.2.0] — 2026-05-14 (existing-project drift+fix+verify+export pipeline)

### Added
- `pipeline/scan_code.py` — Python AST → public_classes/functions/signatures per module
- `pipeline/scan_docs.py` — markdown → frontmatter + wikilinks + code_refs + symbol_mentions; manual_edit detection
- `pipeline/drift.py` — 4-type drift detector (gap / orphan / symbol_drift / claim_drift) with filesystem orphan check, dominant-extension filter, CJK-aware
- `pipeline/fix.py` — drift report → PM ticket plan (one ticket per drift type per affected doc)
- `pipeline/verify.py` — rubric-driven verification with 6 named verifier functions (hallucination/accuracy/completeness/cross_link/examples/structure)
- `pipeline/export.py` — 3 destinations with upsert semantics:
  - `obsidian` → ~/Documents/Obsidian/<project>/ (manual_edit pages preserved)
  - `notebooklm` → notebook named <project> (existing reused, missing created)
  - `graphify` → <project>/.vault-builder/graphify-out/
- `agents/gap-filler.md` — create new doc for undocumented module
- `agents/orphan-pruner.md` — mark/remove dead refs
- `agents/drift-fixer.md` — sync signature/symbol to current code
- `commands/vault-drift.md` — read-only drift diagnostic
- `commands/vault-build.md` — rewritten: 5-phase CWD-based pipeline (scan→drift→fix→verify→export)
- `tests/test_drift.py` (8 cases) + `tests/test_fix_verify_export.py` (7 cases)

### Changed
- `rubrics/code-docs.yaml`: dim weights rebalanced to sum 100 (was 110)
- `commands/vault-build.md`: refocused from "build vault from scratch" to "improve existing project docs + export"

### Status
- Tests: 53 passing (was 46)
- Selftest: 10/10 PASS
- ga4-collector dogfood: 8 gap + 44 orphan + 22 claim drift detected; verify 33.3/100 (real signal); obsidian export created 15 pages
- nbm regression: 100/100 / 100/100 (no regression)

## [0.1.0] — 2026-05-14 (initial unified plugin)
- Subsumed notebooklm-vault-builder + autonomous-docs-loop + sportic365 kb-update
- Source adapter pattern (notebooklm + code)
- 24 agents + kernel scripts (ticket/cost/lock/backup/selftest)
- 38 tests, 10/10 selftest

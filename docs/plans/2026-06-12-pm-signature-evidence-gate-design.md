# PM-SIGNATURE Evidence Gate Design

**Goal:** A successful phase-end must fail closed when a gate-critical contract round lacks a valid `PM-SIGNATURE`.

## Context

Run-4 Phase 2 produced successful phase state while its active contract rounds lacked `PM-SIGNATURE`. `scripts/_dogfood_gate.py` caught the missing signatures, but `scripts/_evidence.py::gate_phase_end()` passed because it validated frozen diff, tickets, reviewer outputs, and verdicts without validating the PM signature chain.

## Chosen Approach

Add PM-signature verification to the phase-end evidence chain and to task-dispatch hook gating when a contract marker is present.

- `scripts/_evidence.py::assert_round_evidence()` calls `_contract.verify_pm_signature(contract_dir)` before reviewer evidence can count.
- Missing, unreadable, or tampered signatures are converted into `EvidenceError`, so `gate_phase_end()` returns `evidence_failed`.
- `hooks/dispatch-contract-gate.sh` also requires a valid signature for marked contract dispatches, preventing known-bad contract dirs from reaching subagents.

## Non-goals

- Do not redesign `contract-check.json`.
- Do not move the PM loop into a Python FSM in this change.
- Do not repair historical `.planning` artifacts; they should fail if revalidated.

## Testing

Use TDD:

1. Add failing `tests/test_evidence.py` coverage for missing and tampered `PM-SIGNATURE`.
2. Add failing hook self-test coverage for dispatch marker + missing signature.
3. Implement minimal code.
4. Run focused tests, hook self-test, type/lint gates, and module-size/doc-integrity gates.

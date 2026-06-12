# Harness hardening design — evidence protocol + headless recovery

Date: 2026-06-12
Status: approved for planning

## Problem

The evidence-chain smoke run validated the new PM-SIGNATURE and `contract-check.json` gates, but exposed three harness defects:

1. The PM protocol did not explicitly require `orchestrator.py dispatch-contract-check --contract <contract.json>` between `PM-SIGNATURE` creation and ticket preparation.
2. Reviewer dispatch is only safe when prompts carry a literal ticket marker (`TICKET=<ticket_path>`) plus `contract_dir=<contract_dir>`; this needs to stay pinned in PM-facing protocol text.
3. `scripts/headless-loop.py` treats any `claude -p` timeout (`rc == 124`) as phase failure, even when the PM already advanced state to a successful phase before the wrapper timed out.

## Decision

Split the fix into two PRs.

### PR-A — evidence/protocol hardening

Make the intended trust chain explicit and regression-pinned:

```text
write contract.json
→ write PM-SIGNATURE
→ run orchestrator.py dispatch-contract-check --contract <contract.json>
→ create/validate contract-check.json
→ call _dispatch.prepare_subagent_ticket(...)
→ dispatch with prompt markers:
   TICKET=<ticket_path>
   contract_dir=<contract_dir>
```

This PR should not add a parallel trust mechanism. `_dispatch.prepare_subagent_ticket()` and `hooks/dispatch-contract-gate.sh` already fail closed when `contract-check.json`, `PM-SIGNATURE`, or ticket markers are absent/stale. The PR pins PM instructions so the PM reliably follows the gate path.

### PR-B — headless runtime recovery hardening

Make timeout handling state-aware:

```text
run_claude_session(...) returns rc
→ reload state
→ accumulate usage
→ if rc == 124:
     if state already records success or the active phase has ended successfully:
        preserve state and return the recorded status
     else:
        keep existing fail-closed timeout path
```

This prevents a late wrapper timeout from overwriting a completed phase. It must not turn stranded reviewer outputs into success; phase-end evidence gates remain the authority for success.

## Data flow

### Dispatch trust chain

The PM writes contract artifacts in the contract directory. `dispatch-contract-check` writes `contract-check.json` beside `contract.json`, including the contract hash and PM-SIGNATURE status. Ticket preparation then verifies the signature, snapshots, preflight artifact, and contract-check artifact before writing `<contract_dir>/tickets/<role>.json`.

Reviewer dispatch must include both `TICKET=` and `contract_dir=` markers. Hooks derive the contract directory from those markers and reject reviewer dispatch during an active run when the dispatch is not bound to a signed, checked contract.

### Headless timeout path

The headless driver owns only the outer process lifetime. The PM session owns state transitions via `orchestrator.py phase-start` and `phase-end`. Therefore, after a timeout, the driver must inspect persisted state before writing a failure status. If the persisted state already proves success, the driver preserves it; otherwise it uses the existing non-destructive failure path and stashes dirty root changes.

## Failure handling

- `dispatch-contract-check` fails: no ticket dispatch.
- `contract-check.json` missing or stale: `prepare_subagent_ticket()` and hook gates reject.
- `PM-SIGNATURE` missing or stale: contract-check/ticket/evidence gates reject.
- Reviewer prompt missing `TICKET=` during an active run: hook rejects.
- Reviewer output missing: phase-end evidence gate rejects success.
- True headless timeout with state still running: mark failed as today.
- Late timeout after successful phase-end: preserve the recorded state.

## Test strategy

### PR-A

Add prompt/protocol regression coverage that verifies `agents/pm-orchestrator.md` preserves:

- `orchestrator.py dispatch-contract-check --contract`
- `_dispatch.prepare_subagent_ticket`
- `TICKET={ticket_path}`
- `contract_dir={contract_dir}`
- ordering: dispatch-contract-check appears before ticket preparation in the contract dispatch protocol.

Run existing gate coverage:

- `tests/test_beta_dispatch.py`
- `hooks/test_dispatch_contract_gate.py`

### PR-B

Add headless-loop regression coverage:

- `rc == 124` plus persisted `status=success` returns success and does not overwrite state.
- `rc == 124` plus active phase already ended with success while run remains non-terminal preserves the state instead of marking failed.
- `rc == 124` plus state still running keeps the current fail-closed timeout behavior.
- Initial `current_phase=0` renders the next execution phase as `1`, not `0`, in prompts/trailers.

## Out of scope

- Live Codex behavior changes.
- Tracking `.planning/auto-pilot/` evidence artifacts in git.
- Re-running a live dogfood smoke inside either implementation PR.
- Replacing the existing evidence gate authority.

# Contract-Check PM-SIGNATURE Status Design

**Goal:** Make `contract-check.json` record the verified `PM-SIGNATURE` state so dispatch failures show whether the contract bytes, signature bytes, and manifest binding were checked before subagent dispatch.

## Problem

Approach A made phase-end and dispatch fail closed on invalid `PM-SIGNATURE`, but `contract-check.json` still only recorded `contract_sha256`. A stale or legacy artifact can look superficially complete until a later independent signature check fails.

## Design

- Add a small helper module, `scripts/_contract_check.py`, as the single producer/validator for `contract-check.json`.
- `orchestrator.py dispatch-contract-check` writes:
  - `contract_sha256`
  - `checked_at`
  - `schema_version`
  - `result: pass`
  - `pm_signature.verified: true`
  - `pm_signature.signature_sha256`
  - `pm_signature.contract_sha256`
  - `pm_signature.manifest_sha256`
- The helper verifies `PM-SIGNATURE` before producing a pass artifact.
- `_dispatch.prepare_subagent_ticket()` rejects legacy/stale artifacts via the helper before ticket creation.
- `dispatch-contract-gate.sh` rejects legacy/stale signature-status artifacts, then still recomputes `PM-SIGNATURE` independently.

## Non-goals

- No new JSON schema file unless a future reader needs standalone validation.
- No phase FSM rewrite.
- No weakening of Approach A's independent signature verification.

# Contract-Check PM-SIGNATURE Status Implementation Plan

## Task 1 — Artifact producer RED/GREEN

1. Add tests that `dispatch-contract-check` records `pm_signature` status fields.
2. Add a test that missing `PM-SIGNATURE` makes `dispatch-contract-check` return non-zero and avoids writing a pass artifact.
3. Implement `scripts/_contract_check.py` artifact building and wire `orchestrator.py` to it.

## Task 2 — Python dispatch gate RED/GREEN

1. Add tests that `_dispatch.prepare_subagent_ticket()` rejects:
   - legacy `contract-check.json` with no `pm_signature` object
   - stale `pm_signature.signature_sha256`
2. Update `_dispatch._check_contract_check_artifact()` to delegate artifact freshness validation to `scripts/_contract_check.py`.

## Task 3 — Hook dispatch gate RED/GREEN

1. Add/update hook fixtures so valid dispatches include signature-status artifacts.
2. Add a hook self-test that a legacy artifact with valid SHA but missing `pm_signature` is denied.
3. Update `hooks/dispatch-contract-gate.sh` to verify the signature-status fields before its independent `PM-SIGNATURE` recomputation.

## Task 4 — Verify

Run:

```bash
python3 -m pytest tests/test_beta_dispatch.py tests/test_hooks_auth.py -q
python3 hooks/test_dispatch_contract_gate.py
python3 -m pytest tests/ -q
python3 -m ruff check scripts/ tests/ hooks/
python3 -m mypy scripts/ hooks/
bash scripts/quality/check-module-size.sh
python3 scripts/docs/check_doc_reference_integrity.py
```

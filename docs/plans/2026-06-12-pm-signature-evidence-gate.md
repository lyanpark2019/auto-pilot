# PM-SIGNATURE Evidence Gate Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make phase-end success and marked contract dispatch fail when `PM-SIGNATURE` is missing or invalid.

**Architecture:** Treat `PM-SIGNATURE` as part of the same evidence chain as frozen diff SHA, reviewer tickets, and reviewer verdicts. The final phase-end gate recomputes the signature with `_contract.verify_pm_signature()`, and the dispatch hook rejects marked contract dirs before subagents run.

**Tech Stack:** Python stdlib, pytest, bash hook self-tests, existing `_contract` helpers.

---

### Task 1: Add RED tests for phase-end signature enforcement

**Files:**
- Modify: `tests/test_evidence.py`

**Step 1:** Extend the round fixture so it can create a valid context bundle, contract JSON, and `PM-SIGNATURE` by default.

**Step 2:** Add tests:
- missing `PM-SIGNATURE` rejects `assert_round_evidence()`
- tampered `PM-SIGNATURE` rejects `assert_round_evidence()`
- `gate_phase_end()` returns `evidence_failed` for an unsigned active round

**Step 3:** Run:

```bash
python3 -m pytest tests/test_evidence.py -q
```

Expected: new tests fail because `_evidence.py` does not yet verify signatures.

### Task 2: Implement evidence-gate signature verification

**Files:**
- Modify: `scripts/_evidence.py`

**Step 1:** Call `_contract.verify_pm_signature(contract_dir)` in `assert_round_evidence()` after `contract.json` presence is established.

**Step 2:** Convert `OSError`, `json.JSONDecodeError`, `KeyError`, and `_contract.PMSignatureMismatchError` into `EvidenceError` failure text.

**Step 3:** Run:

```bash
python3 -m pytest tests/test_evidence.py tests/test_contract.py tests/test_dogfood_gate.py -q
```

Expected: pass.

### Task 3: Add RED hook coverage for missing signature

**Files:**
- Modify: `hooks/test_dispatch_contract_gate.py`

**Step 1:** Add a fixture path where `contract.json`, `contract-check.json`, and preflight pass but `PM-SIGNATURE` is absent.

**Step 2:** Add a case expecting DENY.

**Step 3:** Run:

```bash
python3 hooks/test_dispatch_contract_gate.py
```

Expected: new case fails because the hook does not yet check the signature.

### Task 4: Implement dispatch hook signature verification

**Files:**
- Modify: `hooks/dispatch-contract-gate.sh`

**Step 1:** After `contract-check.json` sha verification, run a Python one-liner importing `scripts/_contract.py` and calling `verify_pm_signature(Path(contract_dir))`.

**Step 2:** Deny on non-zero exit with a message that mentions `PM-SIGNATURE`.

**Step 3:** Run:

```bash
python3 hooks/test_dispatch_contract_gate.py
```

Expected: pass.

### Task 5: Verify and commit

Run:

```bash
python3 -m pytest tests/test_evidence.py tests/test_contract.py tests/test_dogfood_gate.py -q
python3 hooks/test_dispatch_contract_gate.py
python3 -m ruff check scripts/_evidence.py tests/test_evidence.py hooks/test_dispatch_contract_gate.py
python3 -m mypy scripts/_evidence.py
bash scripts/quality/check-module-size.sh
python3 scripts/docs/check_doc_reference_integrity.py
```

Commit path-specific files only.

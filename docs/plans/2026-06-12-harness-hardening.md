# Harness Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Harden the auto-pilot harness so PM dispatch follows the signed contract-check path and headless wrapper timeouts cannot overwrite completed phase state.

**Architecture:** Ship two PRs. PR-A is a protocol/test pin that makes `dispatch-contract-check` and literal ticket markers explicit in PM instructions. PR-B is a state-machine change in `scripts/headless-loop.py` that preserves persisted success after late wrapper timeouts while keeping true timeouts fail-closed.

**Tech Stack:** Python 3, pytest, bash hook self-tests, Markdown protocol docs, Claude plugin manifests.

---

## Preconditions

- Start from clean `main` synced to `origin/main`.
- Preserve untracked `.claude/routing/`; do not add or delete it.
- Use separate branches/worktrees:
  - PR-A: `fix/dispatch-contract-protocol-pin`
  - PR-B: `fix/headless-timeout-state-preserve`
- Do not use `git add .`; add exact paths only.
- Before any push/PR/merge, run:
  ```bash
  ACTIVE=$(gh api user --jq .login); [ "$ACTIVE" = "lyanpark2019" ] || gh auth switch --hostname github.com --user lyanpark2019
  ```

---

## PR-A — Evidence/protocol hardening

### Task A1: Write failing PM protocol regression tests

**Files:**
- Create: `tests/test_pm_protocol_contract_dispatch.py`
- Read: `agents/pm-orchestrator.md`

**Step 1: Create the test file**

```python
"""Regression pins for PM contract dispatch protocol.

These tests protect the evidence chain documented after the 2026-06-12
live smoke: PM-SIGNATURE must be followed by dispatch-contract-check before
any subagent ticket is prepared, and live dispatch prompts must carry literal
TICKET/contract_dir markers.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PM_ORCHESTRATOR = ROOT / "agents" / "pm-orchestrator.md"


def _contract_dispatch_protocol() -> str:
    text = PM_ORCHESTRATOR.read_text()
    start = text.index("## Contract dispatch protocol (v1)")
    end = text.index("## Merge conflict state machine (v1)")
    return text[start:end]


def test_pm_protocol_runs_contract_check_before_ticket_prep() -> None:
    section = _contract_dispatch_protocol()
    contract_check = "orchestrator.py dispatch-contract-check --contract"
    ticket_prep = "_dispatch.prepare_subagent_ticket"

    assert contract_check in section
    assert ticket_prep in section
    assert section.index(contract_check) < section.index(ticket_prep)


def test_pm_protocol_pins_ticket_and_contract_dir_markers() -> None:
    section = _contract_dispatch_protocol()

    assert "TICKET={ticket_path}" in section
    assert "contract_dir={contract_dir}" in section
```

**Step 2: Run test to verify it fails**

Run:
```bash
python3 -m pytest tests/test_pm_protocol_contract_dispatch.py -q
```

Expected before implementation: first test fails because `dispatch-contract-check` is absent from the protocol section.

### Task A2: Update PM contract dispatch protocol

**Files:**
- Modify: `agents/pm-orchestrator.md`

**Step 1: Edit the protocol list**

In `## Contract dispatch protocol (v1)`, update the sequence so it explicitly reads:

```markdown
3. PM writes PM-SIGNATURE via `_contract.write_pm_signature(contract_dir, run_id=state["run_id"])`
4. PM runs `python3 scripts/orchestrator.py dispatch-contract-check --contract "$contract_dir/contract.json"` and verifies the JSON response has `"ok": true`; any non-zero exit or missing/stale `contract-check.json` stops dispatch.
5. PM calls `_dispatch.prepare_subagent_ticket(contract_dir, worktree, subagent_role, diff_path=None)` per subagent
6. PM Agent-dispatches with prompt template (the `contract_dir=` marker is what
   `hooks/dispatch-contract-gate.sh` keys on; the hook also derives it from
   `TICKET=` as fallback — keep both lines):
```

Renumber the following steps accordingly:

```markdown
7. After worker DONE, PM calls `_dispatch.freeze_diff_for_review(...)`
8. PM calls `_dispatch.collect_round_outcome(...)`
9. After each reviewer, PM calls `_dispatch.assert_reviewer_was_scoped(...)`
```

**Step 2: Keep the literal markers unchanged**

The fenced prompt template must still include:

```text
TICKET={ticket_path}
contract_dir={contract_dir}
```

Do not replace these with prose or alternate variable names.

### Task A3: Run PR-A targeted verification

**Files:**
- Test: `tests/test_pm_protocol_contract_dispatch.py`
- Test: `tests/test_beta_dispatch.py`
- Test: `hooks/test_dispatch_contract_gate.py`

Run:
```bash
python3 -m pytest tests/test_pm_protocol_contract_dispatch.py tests/test_beta_dispatch.py -q
python3 hooks/test_dispatch_contract_gate.py
python3 -m ruff check tests/test_pm_protocol_contract_dispatch.py
```

Expected: pytest passes, hook self-test reports `9/9 passed`, ruff passes.

### Task A4: Commit PR-A

Run:
```bash
git add agents/pm-orchestrator.md tests/test_pm_protocol_contract_dispatch.py
git commit -m "fix: pin dispatch contract protocol" -m "Require the PM protocol to run dispatch-contract-check before ticket preparation and preserve literal TICKET/contract_dir dispatch markers.\n\nRejected: rely on prose-only memory of the live smoke defect | regression pins make the trust-chain step durable\nConstraint: protocol/test-only PR; runtime gates already fail closed in _dispatch and hooks\nNot-tested: live auto-pilot dogfood not rerun in this PR\nConfidence: high"
```

### Task A5: Push PR-A and wait for CI

Run:
```bash
ACTIVE=$(gh api user --jq .login); [ "$ACTIVE" = "lyanpark2019" ] || gh auth switch --hostname github.com --user lyanpark2019
git push -u origin fix/dispatch-contract-protocol-pin
ACTIVE=$(gh api user --jq .login); [ "$ACTIVE" = "lyanpark2019" ] || gh auth switch --hostname github.com --user lyanpark2019
gh pr create --base main --head fix/dispatch-contract-protocol-pin --title "fix: pin dispatch contract protocol" --body-file - <<'EOF'
## Summary
- require PM protocol to run dispatch-contract-check before preparing tickets
- pin literal TICKET and contract_dir dispatch markers
- add regression tests for protocol ordering and markers

## Verification
- `python3 -m pytest tests/test_pm_protocol_contract_dispatch.py tests/test_beta_dispatch.py -q`
- `python3 hooks/test_dispatch_contract_gate.py`
- `python3 -m ruff check tests/test_pm_protocol_contract_dispatch.py`
EOF
ACTIVE=$(gh api user --jq .login); [ "$ACTIVE" = "lyanpark2019" ] || gh auth switch --hostname github.com --user lyanpark2019
gh pr checks --watch --interval 10
```

If green but branch policy blocks self-authored merge, use admin merge only after confirming every check is successful.

---

## PR-B — Headless runtime recovery hardening

Start PR-B only after PR-A is merged and local `main` is fast-forwarded to `origin/main`.

### Task B1: Add failing timeout preservation tests

**Files:**
- Modify: `tests/test_headless_loop.py`

**Step 1: Add success-preservation test**

Append near existing timeout tests:

```python
def test_timeout_preserves_terminal_success_state(loop_module, state_dir):
    """A wrapper timeout after PM recorded success must not rewrite state to failed."""
    _write_state(state_dir, status="running")
    args = _args()

    def _session(prompt, log_path, timeout_sec):
        (state_dir / "state.json").write_text(json.dumps({
            "status": "success",
            "current_phase": 2,
            "total_phases": 2,
            "phases": [{
                "phase": 2,
                "status": "success",
                "round": 1,
                "contracts": 1,
                "approved": 1,
                "started": "2026-06-12T00:00:00+00:00",
                "ended": "2026-06-12T00:01:00+00:00",
                "commits": ["abc123"],
            }],
        }))
        return 124

    with patch.object(loop_module, "run_claude_session", side_effect=_session), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module, "stash_if_dirty") as stash:
        result = loop_module.loop_iteration(1, args)

    assert result == "success"
    stash.assert_not_called()
    assert json.loads((state_dir / "state.json").read_text())["status"] == "success"
```

**Step 2: Add phase-success preservation test**

```python
def test_timeout_preserves_completed_phase_when_run_continues(loop_module, state_dir):
    """A completed non-final phase should survive rc=124 so the next iteration can advance."""
    _write_state(state_dir, status="running")
    args = _args()

    def _session(prompt, log_path, timeout_sec):
        (state_dir / "state.json").write_text(json.dumps({
            "status": "running",
            "current_phase": 1,
            "total_phases": 2,
            "phases": [{
                "phase": 1,
                "status": "success",
                "round": 1,
                "contracts": 1,
                "approved": 1,
                "started": "2026-06-12T00:00:00+00:00",
                "ended": "2026-06-12T00:01:00+00:00",
                "commits": ["abc123"],
            }],
        }))
        return 124

    with patch.object(loop_module, "run_claude_session", side_effect=_session), \
         patch.object(loop_module, "git_head", return_value="abc123"), \
         patch.object(loop_module, "stash_if_dirty") as stash:
        result = loop_module.loop_iteration(1, args)

    assert result == "running"
    stash.assert_not_called()
    assert json.loads((state_dir / "state.json").read_text())["status"] == "running"
```

**Step 3: Run tests to verify they fail**

Run:
```bash
python3 -m pytest tests/test_headless_loop.py::test_timeout_preserves_terminal_success_state tests/test_headless_loop.py::test_timeout_preserves_completed_phase_when_run_continues -q
```

Expected before implementation: both fail because timeout handling overwrites state to `failed`.

### Task B2: Add next-phase prompt semantics tests

**Files:**
- Modify: `tests/test_headless_loop.py`

**Step 1: Add helper tests**

```python
def test_phase_for_next_session_initial_state_is_phase_one(loop_module):
    assert loop_module.phase_for_next_session({"current_phase": 0, "total_phases": 2}) == 1


def test_phase_for_next_session_advances_after_completed_nonfinal_phase(loop_module):
    state = {
        "status": "running",
        "current_phase": 1,
        "total_phases": 2,
        "phases": [{"phase": 1, "status": "success"}],
    }

    assert loop_module.phase_for_next_session(state) == 2


def test_phase_for_next_session_keeps_running_phase(loop_module):
    state = {
        "status": "running",
        "current_phase": 1,
        "total_phases": 2,
        "phases": [{"phase": 1, "status": "running"}],
    }

    assert loop_module.phase_for_next_session(state) == 1
```

**Step 2: Run tests to verify they fail**

Run:
```bash
python3 -m pytest tests/test_headless_loop.py::test_phase_for_next_session_initial_state_is_phase_one tests/test_headless_loop.py::test_phase_for_next_session_advances_after_completed_nonfinal_phase tests/test_headless_loop.py::test_phase_for_next_session_keeps_running_phase -q
```

Expected before implementation: fail because `phase_for_next_session` does not exist.

### Task B3: Implement phase selection helper

**Files:**
- Modify: `scripts/headless-loop.py`

**Step 1: Add helper near `commit_trailer`**

```python
def phase_for_next_session(state: State) -> int:
    """Return the phase number the next headless PM session should execute."""
    current = int(state.get("current_phase", 0) or 0)
    total = int(state.get("total_phases", 0) or 0)
    if current < 1:
        return 1
    phases = state.get("phases", [])
    active = phases[-1] if phases else None
    if (
        active is not None
        and active.get("phase") == current
        and active.get("status") == "success"
        and current < total
    ):
        return current + 1
    return current
```

**Step 2: Use helper in `loop_iteration`**

Replace:

```python
phase = state.get("current_phase", 0)
```

with:

```python
phase = phase_for_next_session(state)
```

### Task B4: Implement timeout success preservation

**Files:**
- Modify: `scripts/headless-loop.py`

**Step 1: Add helper near `_handle_timeout`**

```python
def _completed_active_phase(state: State) -> bool:
    current = int(state.get("current_phase", 0) or 0)
    phases = state.get("phases", [])
    active = phases[-1] if phases else None
    return bool(
        active is not None
        and active.get("phase") == current
        and active.get("status") == "success"
        and active.get("ended")
    )


def _timeout_preserved_status(state_after: State) -> str | None:
    status = state_after.get("status")
    if status == "success":
        return "success"
    if status == "running" and _completed_active_phase(state_after):
        return "running"
    return None
```

**Step 2: Use helper in timeout branch**

Replace:

```python
if rc == 124:
    return _handle_timeout(iter_n, pre_head, state_after)
```

with:

```python
if rc == 124:
    preserved = _timeout_preserved_status(state_after)
    if preserved is not None:
        event("iter.timeout_preserved_state", n=iter_n, status=preserved)
        return preserved
    return _handle_timeout(iter_n, pre_head, state_after)
```

### Task B5: Run PR-B targeted tests

Run:
```bash
python3 -m pytest tests/test_headless_loop.py tests/test_headless_loop_cli.py -q
python3 -m ruff check scripts/headless-loop.py tests/test_headless_loop.py tests/test_headless_loop_cli.py
python3 -m mypy scripts/headless-loop.py
```

Expected: all pass.

### Task B6: Run trust-chain regression tests after runtime change

Run:
```bash
python3 -m pytest tests/test_evidence.py tests/test_beta_dispatch.py -q
python3 hooks/test_dispatch_contract_gate.py
```

Expected: all pass; missing reviewer outputs remain blocked by the evidence gate.

### Task B7: Commit PR-B

Run:
```bash
git add scripts/headless-loop.py tests/test_headless_loop.py
git commit -m "fix: preserve completed state after headless timeout" -m "Make headless timeout handling consult persisted state before marking a run failed, and compute the next execution phase from state so phase 0 is not dispatched.\n\nRejected: always treat rc=124 as failed | live smoke showed the PM can complete and persist success before the wrapper timeout fires\nConstraint: preserve fail-closed behavior unless state already proves success/completed phase\nNot-tested: live dogfood smoke not rerun; covered by state-machine unit tests and evidence-gate regressions\nConfidence: medium"
```

### Task B8: Push PR-B and wait for CI

Run:
```bash
ACTIVE=$(gh api user --jq .login); [ "$ACTIVE" = "lyanpark2019" ] || gh auth switch --hostname github.com --user lyanpark2019
git push -u origin fix/headless-timeout-state-preserve
ACTIVE=$(gh api user --jq .login); [ "$ACTIVE" = "lyanpark2019" ] || gh auth switch --hostname github.com --user lyanpark2019
gh pr create --base main --head fix/headless-timeout-state-preserve --title "fix: preserve completed state after headless timeout" --body-file - <<'EOF'
## Summary
- preserve persisted success when the outer headless wrapper times out late
- compute next execution phase from state so initial runs use phase 1, not phase 0
- keep true timeouts fail-closed when state does not prove completion

## Verification
- `python3 -m pytest tests/test_headless_loop.py tests/test_headless_loop_cli.py -q`
- `python3 -m pytest tests/test_evidence.py tests/test_beta_dispatch.py -q`
- `python3 hooks/test_dispatch_contract_gate.py`
- `python3 -m ruff check scripts/headless-loop.py tests/test_headless_loop.py tests/test_headless_loop_cli.py`
- `python3 -m mypy scripts/headless-loop.py`
EOF
ACTIVE=$(gh api user --jq .login); [ "$ACTIVE" = "lyanpark2019" ] || gh auth switch --hostname github.com --user lyanpark2019
gh pr checks --watch --interval 10
```

If green but branch policy blocks self-authored merge, use admin merge only after confirming every check is successful.

---

## Final verification after both PRs merge

Run on synced `main`:

```bash
python3 -m pytest tests/ -q
python3 -m mypy scripts/ hooks/
python3 -m ruff check scripts/ tests/ hooks/
python3 hooks/test_dispatch_contract_gate.py
bash scripts/quality/check-module-size.sh
python3 scripts/docs/check_doc_reference_integrity.py
claude plugin validate .
```

Expected: all pass. `check_doc_reference_integrity.py` may emit existing warnings, but must report `OK (0 violations)`.

# Run-3 Residuals Gate-then-prove — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the run-3 contract-layer bypass and the headless background-dispatch hole with code-enforced gates, then prove the unproven REJECT-round + merge-conflict loop paths with one headless dogfood run.

**Architecture:** A new `scripts/_evidence.py` module holds the load-bearing exit gate (`assert_round_evidence`) that `orchestrator.py cmd_phase_end` calls before recording `success`. Two shell hooks add defense-in-depth: a reviewer-scoped fail-closed branch in the existing dispatch gate, and a new headless background-dispatch guard. A run-4 spec exercises the gates live.

**Tech Stack:** Python 3 (stdlib + `jsonschema`), Bash (shellcheck-clean, BSD/macOS), pytest, script-style hook self-tests.

**Source spec:** `docs/specs/2026-06-10-run3-residuals-gate-then-prove-design.md`

---

## File Structure

- **Create** `scripts/_evidence.py` — `EvidenceError`, `assert_round_evidence(contract_dir)`, `latest_round_dirs_for_active_phase(contracts_root)`. One responsibility: validate that a review round carries a complete, sha-bound, APPROVE evidence chain. New module (not appended to `_dispatch.py`, which is at 471/500 lines).
- **Modify** `scripts/orchestrator.py` — `cmd_phase_end` calls the gate on `--status success`. (480/500 lines; the call is ~6 lines + 1 import, stays under budget.)
- **Create** `hooks/headless-sync-dispatch-guard.sh` — PreToolUse(Task|Bash) deny when `HARNESS_HEADLESS=1` and `run_in_background == true`.
- **Modify** `hooks/dispatch-contract-gate.sh` — reviewer-scoped fail-closed branch before the marker-absent `exit 0`.
- **Modify** `hooks/hooks.json` — wire the new guard on Task|Bash.
- **Create** `tests/test_evidence.py` — evidence-chain matrix.
- **Create** `tests/test_phase_end_evidence.py` — `cmd_phase_end` refusal/accept paths.
- **Create** `hooks/test_headless_sync_dispatch_guard.py` — guard deny/allow matrix (script-style).
- **Create** `hooks/test_dispatch_contract_gate.py` — reviewer fail-closed deny/allow matrix (script-style).
- **Modify** `tests/test_hooks_wiring.py` — add wiring assertion for the new guard.
- **Modify** `agents/pm-orchestrator.md`, `skills/auto-pilot/SKILL.md` (+ any other "Opus 4.7 main session" occurrences) — model-agnostic reword.
- **Create** `docs/specs/2026-06-10-run4-reject-and-conflict-smoke.md` — live-run input.

---

## Task 1: `_evidence.py` — `assert_round_evidence` core

**Files:**
- Create: `scripts/_evidence.py`
- Test: `tests/test_evidence.py`

Evidence chain (confirmed against real run-3 phase-1 artifacts):
`review-input/frozen.diff.sha256` (text, trailing `\n`) == recomputed
`_contract._sha256(frozen.diff bytes)`; each reviewer `tickets/<role>.json`
has `diff_sha256` == that value; each `outputs/<role>/review.json` is
schema-valid with `verdict == "APPROVE"` and `contract_id` == the round's
`contract.json` `id`.

- [ ] **Step 1: Write the failing test (happy path + each failure mode)**

Create `tests/test_evidence.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _contract  # noqa: E402
import _evidence  # noqa: E402

REVIEWERS = ("codex-reviewer", "claude-reviewer")


def _review(contract_id: str, verdict: str = "APPROVE") -> dict:
    return {
        "schema_version": 1,
        "reviewer": "codex-reviewer",
        "contract_id": contract_id,
        "verdict": verdict,
        "scope_check": "pass",
        "findings": [],
        "verify_rerun": "pass",
        "reviewer_meta": {
            "model": "test",
            "started_at": "2026-06-10T00:00:00+00:00",
            "ended_at": "2026-06-10T00:00:01+00:00",
        },
    }


def _build_round(tmp_path: Path, *, contract_id: str = "iter-1/phase-1/contract-1/round-1",
                 verdict: str = "APPROVE", diff_text: bytes = b"diff --git a b\n",
                 drop: str = "") -> Path:
    """Materialize a contract round dir with a full (or partially broken) evidence chain.

    drop selects a defect: "" (none), "codex-ticket", "claude-review",
    "sha", "verdict", "contract-id".
    """
    cdir = tmp_path / "round-1"
    (cdir / "review-input").mkdir(parents=True)
    (cdir / "tickets").mkdir()
    sha = _contract._sha256(diff_text)
    (cdir / "review-input" / "frozen.diff").write_bytes(diff_text)
    sha_to_write = sha if drop != "sha" else "0" * 64
    (cdir / "review-input" / "frozen.diff.sha256").write_text(sha_to_write + "\n")
    (cdir / "contract.json").write_text(json.dumps({"id": contract_id}))
    for role in REVIEWERS:
        if drop == "codex-ticket" and role == "codex-reviewer":
            continue
        (cdir / "tickets" / f"{role}.json").write_text(json.dumps({"diff_sha256": sha}))
        out = cdir / "outputs" / role
        out.mkdir(parents=True)
        if drop == "claude-review" and role == "claude-reviewer":
            continue
        rid = contract_id if drop != "contract-id" else "iter-9/phase-9/contract-9/round-9"
        v = verdict if drop != "verdict" else "REJECT"
        (out / "review.json").write_text(json.dumps(_review(rid, v)))
    return cdir


def test_full_chain_passes(tmp_path):
    cdir = _build_round(tmp_path)
    _evidence.assert_round_evidence(cdir)  # no raise


@pytest.mark.parametrize("drop", ["codex-ticket", "claude-review", "sha", "verdict", "contract-id"])
def test_each_defect_rejects(tmp_path, drop):
    cdir = _build_round(tmp_path, drop=drop)
    with pytest.raises(_evidence.EvidenceError):
        _evidence.assert_round_evidence(cdir)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_evidence.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named '_evidence'`

- [ ] **Step 3: Write `scripts/_evidence.py`**

```python
"""Exit-gate evidence validation for auto-pilot review rounds.

A review round may only count toward a successful phase when it carries a
complete, sha-bound, dual-APPROVE evidence chain. This is the load-bearing
catch for the run-3 bypass (phase advanced with a missing reviewer ticket and
an empty reviewer output dir, yet state.json recorded APPROVE).

Principle: evidence over trust — the gate recomputes the diff SHA and refuses
trust in any artifact it cannot verify.
"""
from __future__ import annotations

import json
from pathlib import Path

import _contract
import _dispatch

REVIEWERS = ("codex-reviewer", "claude-reviewer")


class EvidenceError(Exception):
    """Raised when a review round's evidence chain is incomplete or inconsistent."""


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def assert_round_evidence(contract_dir: Path) -> None:
    """Raise EvidenceError unless contract_dir holds a complete dual-APPROVE chain.

    Chain: frozen.diff sha matches its recorded .sha256; both reviewer tickets
    bind that sha; both review.json are schema-valid, APPROVE, and carry the
    round's contract id.
    """
    failures: list[str] = []

    frozen = contract_dir / "review-input" / "frozen.diff"
    sha_file = contract_dir / "review-input" / "frozen.diff.sha256"
    contract_file = contract_dir / "contract.json"

    if not frozen.exists() or not sha_file.exists():
        raise EvidenceError(f"{contract_dir}: missing frozen.diff or frozen.diff.sha256")
    if not contract_file.exists():
        raise EvidenceError(f"{contract_dir}: missing contract.json")

    recorded_sha = sha_file.read_text().strip()
    actual_sha = _contract._sha256(frozen.read_bytes())
    if recorded_sha != actual_sha:
        failures.append(f"frozen.diff sha mismatch (recorded={recorded_sha}, actual={actual_sha})")

    contract_id = str(_read_json(contract_file).get("id") or "")

    for role in REVIEWERS:
        ticket = contract_dir / "tickets" / f"{role}.json"
        review = contract_dir / "outputs" / role / "review.json"
        if not ticket.exists():
            failures.append(f"{role}: ticket missing")
        else:
            ticket_sha = str(_read_json(ticket).get("diff_sha256") or "")
            if ticket_sha != actual_sha:
                failures.append(f"{role}: ticket diff_sha256 != frozen.diff sha")
        if not review.exists():
            failures.append(f"{role}: review.json missing")
            continue
        try:
            data = _dispatch.read_review(review)
        except _dispatch.MalformedReviewError as exc:
            failures.append(f"{role}: review.json schema-invalid: {exc}")
            continue
        if data.get("verdict") != "APPROVE":
            failures.append(f"{role}: verdict={data.get('verdict')!r} (need APPROVE)")
        if str(data.get("contract_id") or "") != contract_id:
            failures.append(f"{role}: contract_id {data.get('contract_id')!r} != {contract_id!r}")

    if failures:
        raise EvidenceError(f"{contract_dir}: " + "; ".join(failures))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_evidence.py -q`
Expected: PASS (6 tests: 1 happy + 5 parametrized defects)

- [ ] **Step 5: Run the real run-3 fixtures as a sanity check (manual, no commit)**

Run:
```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import _evidence
from pathlib import Path
good = Path('.planning/auto-pilot/contracts/iter-1/phase-1/contract-1/round-1')
bad  = Path('.planning/auto-pilot/contracts/iter-1/phase-2/contract-1/round-1')
_evidence.assert_round_evidence(good); print('phase-1 GOOD: passed (correct)')
try:
    _evidence.assert_round_evidence(bad); print('phase-2 BAD: passed (WRONG)')
except _evidence.EvidenceError as e:
    print('phase-2 BAD: rejected (correct) ->', str(e)[:120])
"
```
Expected: phase-1 passes, phase-2 rejected (missing codex ticket + claude review).

- [ ] **Step 6: Commit**

```bash
git add scripts/_evidence.py tests/test_evidence.py
AUTO_PILOT_MAIN_OK=1 git commit -m "feat(evidence): assert_round_evidence exit gate (sha-bound dual-APPROVE chain)

Closes run-3 bypass at the evidence layer: a review round must carry
frozen.diff sha == recorded sha, both reviewer tickets binding that sha,
and both review.json APPROVE with matching contract_id.

Not-tested: not yet wired into cmd_phase_end (Task 3)
Confidence: high"
```

---

## Task 2: `latest_round_dirs_for_active_phase` — locate the phase's contracts

**Files:**
- Modify: `scripts/_evidence.py`
- Test: `tests/test_evidence.py`

The auto-pilot loop runs phases sequentially, so when a phase is being closed
the highest-numbered `phase-<N>` dir in the contracts tree IS that phase
(the next phase has not started). For each contract under it, the latest
`round-*` is the one that must hold the APPROVE evidence.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evidence.py`:

```python
def test_latest_round_dirs_picks_max_phase_latest_round(tmp_path):
    root = tmp_path / "contracts"
    # phase-1 (older), phase-2 (current); phase-2/contract-1 has rounds 1 and 2
    for rel in [
        "iter-1/phase-1/contract-1/round-1",
        "iter-1/phase-2/contract-1/round-1",
        "iter-1/phase-2/contract-1/round-2",
        "iter-1/phase-2/contract-2/round-1",
    ]:
        (root / rel).mkdir(parents=True)
    dirs = _evidence.latest_round_dirs_for_active_phase(root)
    names = sorted(str(d.relative_to(root)) for d in dirs)
    assert names == [
        "iter-1/phase-2/contract-1/round-2",
        "iter-1/phase-2/contract-2/round-1",
    ]


def test_latest_round_dirs_empty_when_no_contracts(tmp_path):
    assert _evidence.latest_round_dirs_for_active_phase(tmp_path / "nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_evidence.py -k latest_round -q`
Expected: FAIL — `AttributeError: module '_evidence' has no attribute 'latest_round_dirs_for_active_phase'`

- [ ] **Step 3: Implement the helper**

Append to `scripts/_evidence.py`:

```python
def _phase_num(phase_dir: Path) -> int:
    try:
        return int(phase_dir.name.split("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def latest_round_dirs_for_active_phase(contracts_root: Path) -> list[Path]:
    """Return the latest round-* dir of each contract under the highest phase-N.

    Sequential phase execution means the max phase dir present is the one being
    closed. Returns [] when no contracts tree exists.
    """
    if not contracts_root.exists():
        return []
    phase_dirs: list[Path] = []
    for iter_dir in sorted(contracts_root.glob("iter-*")):
        phase_dirs.extend(p for p in iter_dir.glob("phase-*") if p.is_dir())
    if not phase_dirs:
        return []
    max_phase = max(_phase_num(p) for p in phase_dirs)
    out: list[Path] = []
    for phase_dir in phase_dirs:
        if _phase_num(phase_dir) != max_phase:
            continue
        for contract_dir in sorted(phase_dir.glob("contract-*")):
            rounds = sorted(contract_dir.glob("round-*"), key=lambda d: d.name)
            if rounds:
                out.append(rounds[-1])
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_evidence.py -q`
Expected: PASS (8 tests total)

- [ ] **Step 5: Commit**

```bash
git add scripts/_evidence.py tests/test_evidence.py
AUTO_PILOT_MAIN_OK=1 git commit -m "feat(evidence): latest_round_dirs_for_active_phase locator

Picks the latest round of each contract under the max phase-N dir (correct
for sequential phase execution — next phase has not started at phase-end).

Constraint: assumes sequential phase order (the auto-pilot loop invariant)
Confidence: high"
```

---

## Task 3: Wire the exit gate into `cmd_phase_end`

**Files:**
- Modify: `scripts/orchestrator.py:169-184` (`cmd_phase_end`)
- Test: `tests/test_phase_end_evidence.py`

When `--status success`, every latest-round dir of the active phase must pass
`assert_round_evidence` before state is written. Failure → print `BLOCKED ...`
to stderr, return 2, write nothing. `failed`/`pivot-needed` are exempt. An
opt-out env `AUTO_PILOT_SKIP_EVIDENCE=1` exists ONLY for the dogfood-gate
unit tests that fabricate state without contract dirs (documented escape hatch,
not for live runs).

- [ ] **Step 1: Write the failing test**

Create `tests/test_phase_end_evidence.py`:

```python
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ORCH = str(Path(__file__).resolve().parent.parent / "scripts" / "orchestrator.py")


def _run(cwd: Path, *args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    import os
    # _state.STATE_DIR is the RELATIVE path ".planning/auto-pilot" — it resolves
    # against the subprocess CWD, so running with cwd=tmp_path isolates state.
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run([sys.executable, ORCH, *args], cwd=cwd,
                          capture_output=True, text=True, env=env)


def _init_running_state(cwd: Path) -> None:
    sd = cwd / ".planning" / "auto-pilot"
    sd.mkdir(parents=True)
    (sd / "state.json").write_text(json.dumps({
        "started_at": "2026-06-10T00:00:00+00:00",
        "spec_path": "x.md", "current_phase": 1, "total_phases": 1,
        "status": "running", "max_workers": 1, "time_box_until": None,
        "phases": [{"phase": 1, "status": "running"}],
        "pivot_detector": {}, "cost_usd": 0.0, "tokens": 0,
    }))


def test_phase_end_success_denied_without_evidence(tmp_path):
    _init_running_state(tmp_path)
    # contracts tree exists but the round has NO evidence
    (tmp_path / ".planning/auto-pilot/contracts/iter-1/phase-1/contract-1/round-1").mkdir(parents=True)
    proc = _run(tmp_path, "phase-end", "--phase", "1", "--status", "success")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "BLOCKED" in proc.stderr
    # state untouched — still running
    state = json.loads((tmp_path / ".planning/auto-pilot/state.json").read_text())
    assert state["status"] == "running"


def test_phase_end_failed_is_exempt(tmp_path):
    _init_running_state(tmp_path)
    proc = _run(tmp_path, "phase-end", "--phase", "1", "--status", "failed")
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_phase_end_success_skip_env_allows(tmp_path):
    _init_running_state(tmp_path)
    proc = _run(tmp_path, "phase-end", "--phase", "1", "--status", "success",
                env_extra={"AUTO_PILOT_SKIP_EVIDENCE": "1"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_phase_end_evidence.py -q`
Expected: FAIL — `phase-end --status success` currently returns 0 (no gate yet).

- [ ] **Step 3: Add the gate to `cmd_phase_end`**

In `scripts/orchestrator.py`, add near the top imports (after the `_state` import block):

```python
import os

import _evidence
```

Replace the body of `cmd_phase_end` (currently lines 169-184) so the gate runs
before `_close_phase`:

```python
def cmd_phase_end(args: argparse.Namespace) -> int:
    """Close out the active phase with a final status and commit list."""
    state = load_state()
    if not state or not state.get("phases"):
        event("phase_end.no_active_phase")
        return 2

    current = _active_phase(state)
    if current is None or current["phase"] != args.phase:
        event("phase_end.phase_mismatch", requested=args.phase,
              active=current["phase"] if current else None)
        return 2

    if args.status == "success" and os.environ.get("AUTO_PILOT_SKIP_EVIDENCE") != "1":
        contracts_root = STATE_DIR / "contracts"
        round_dirs = _evidence.latest_round_dirs_for_active_phase(contracts_root)
        if not round_dirs:
            _warn(f"BLOCKED phase-end --status success: no contract round dirs under {contracts_root}")
            event("phase_end.no_evidence_dirs", phase=args.phase)
            return 2
        for round_dir in round_dirs:
            try:
                _evidence.assert_round_evidence(round_dir)
            except _evidence.EvidenceError as exc:
                _warn(f"BLOCKED phase-end --status success: {exc}")
                event("phase_end.evidence_failed", phase=args.phase, detail=str(exc))
                return 2

    _close_phase(current, args.status, args.commits)
    _update_run_status(state, args.status)
    save_state(state)
    _emit_json({"ok": True, "phase": args.phase, "status": args.status}, indent=2)
    return 0
```

> `STATE_DIR` is already imported (line 30 region). If `_warn` is not defined in
> this module, it is — `def _warn` at line 43. Verify both before running.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_phase_end_evidence.py -q`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the dogfood-gate suite to confirm no regression**

Run: `python3 -m pytest tests/ -q -k "dogfood or phase_end or evidence"`
Expected: PASS. If a pre-existing dogfood test calls `phase-end --status success`
on fabricated state, it must set `AUTO_PILOT_SKIP_EVIDENCE=1`; add that env in
the failing test's setup (the escape hatch exists for exactly this).

- [ ] **Step 6: Commit**

```bash
git add scripts/orchestrator.py tests/test_phase_end_evidence.py
AUTO_PILOT_MAIN_OK=1 git commit -m "feat(orchestrator): phase-end success requires round evidence

cmd_phase_end --status success now refuses (exit 2, BLOCKED, no state write)
unless every latest-round dir of the active phase passes assert_round_evidence.
This is the load-bearing fix for the run-3 phase-2 evidence-free advance.

Constraint: AUTO_PILOT_SKIP_EVIDENCE=1 escape hatch for unit tests only
Not-tested: live multi-phase path (proven in Task 9 run-4 dogfood)
Confidence: high"
```

---

## Task 4: `dispatch-contract-gate.sh` — reviewer fail-closed branch

**Files:**
- Modify: `hooks/dispatch-contract-gate.sh:68-69`
- Create: `hooks/test_dispatch_contract_gate.py`

A reviewer dispatch (`subagent_type` contains `auto-pilot-codex-reviewer` or
`auto-pilot-claude-reviewer`) with NO `TICKET=`/`contract_dir=` marker, while an
active run exists (`.planning/auto-pilot/state.json` status `running`), is denied.
Non-reviewer types, no active run, or unparseable input → allow.

- [ ] **Step 1: Write the failing self-test**

Create `hooks/test_dispatch_contract_gate.py`:

```python
#!/usr/bin/env python3
"""Self-test for dispatch-contract-gate.sh reviewer fail-closed branch.

Runs the hook via subprocess with crafted Task tool payloads + a temp cwd that
optionally holds an active-run state.json. ALLOW = silent/exit0 (no "deny" in
stdout); DENY = JSON with permissionDecision deny.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "dispatch-contract-gate.sh")


def _running_state(cwd: Path) -> None:
    sd = cwd / ".planning" / "auto-pilot"
    sd.mkdir(parents=True)
    (sd / "state.json").write_text(json.dumps({"status": "running"}))


def run_case(label, subagent_type, prompt, active_run, expect) -> bool:
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        if active_run:
            _running_state(cwd)
        payload = {"tool_name": "Task",
                   "tool_input": {"subagent_type": subagent_type, "prompt": prompt}}
        result = subprocess.run(["bash", HOOK], input=json.dumps(payload),
                                capture_output=True, text=True, cwd=cwd,
                                env={**os.environ, "PATH": os.environ["PATH"]})
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and "deny" in stdout) else "ALLOW"
    ok = actual == expect
    print(f"[{'OK  ' if ok else 'FAIL'}] {label:48s} expect={expect:5s} got={actual:5s}")
    if not ok:
        print(f"       stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


CASES = [
    ("reviewer, no ticket, active run", "auto-pilot-codex-reviewer", "review this diff", True, "DENY"),
    ("reviewer, no ticket, NO active run", "auto-pilot-codex-reviewer", "review this diff", False, "ALLOW"),
    ("reviewer WITH ticket, active run", "auto-pilot-claude-reviewer",
     "TICKET=/tmp/x/tickets/claude-reviewer.json review", True, "ALLOW"),
    ("non-reviewer (general-purpose), active run", "general-purpose", "do work", True, "ALLOW"),
    ("tech-critic-lead, active run", "tech-critic-lead", "gate contract", True, "ALLOW"),
]


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the self-test to verify it fails**

Run: `python3 hooks/test_dispatch_contract_gate.py`
Expected: FAIL on case 1 (`reviewer, no ticket, active run` → currently ALLOW,
expected DENY) because the marker-absent branch unconditionally exits 0.

- [ ] **Step 3: Insert the reviewer fail-closed branch**

In `hooks/dispatch-contract-gate.sh`, replace the marker-absent line (currently
lines 68-69):

```bash
# No marker at all → allow (non-worker dispatch)
[[ -z "$contract_dir" ]] && exit 0
```

with:

```bash
# No contract marker. Reviewer dispatches are ALWAYS ticketed in the protocol —
# a reviewer subagent_type without a TICKET marker during an active run is an
# ad-hoc bypass of the diff-sha binding → deny. Workers dispatch as
# general-purpose (no reliable type signal) and are caught by the phase-end
# exit gate instead, so they are not gated here.
if [[ -z "$contract_dir" ]]; then
  subagent_type=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("tool_input") or {}).get("subagent_type") or "")
except Exception:
    print("")
' 2>/dev/null || echo "")
  if printf '%s' "$subagent_type" | grep -qE 'auto-pilot-(codex|claude)-reviewer'; then
    state_file="$(pwd)/.planning/auto-pilot/state.json"
    if [[ -f "$state_file" ]]; then
      run_status=$(python3 -c '
import sys, json
try:
    print(json.load(open(sys.argv[1])).get("status") or "")
except Exception:
    print("")
' "$state_file" 2>/dev/null || echo "")
      if [[ "$run_status" == "running" ]]; then
        deny "Reviewer dispatch ($subagent_type) during an active run must carry a TICKET=<path> marker. Prepare it with prepare_subagent_ticket so the review is bound to a frozen diff sha."
      fi
    fi
  fi
  exit 0
fi
```

- [ ] **Step 4: Run the self-test to verify it passes**

Run: `python3 hooks/test_dispatch_contract_gate.py`
Expected: `5/5 passed`

- [ ] **Step 5: Shellcheck the hook**

Run: `shellcheck -S warning hooks/dispatch-contract-gate.sh`
Expected: no output (0 warnings).

- [ ] **Step 6: Commit**

```bash
chmod +x hooks/dispatch-contract-gate.sh
git add hooks/dispatch-contract-gate.sh hooks/test_dispatch_contract_gate.py
AUTO_PILOT_MAIN_OK=1 git commit -m "feat(hook): dispatch-gate denies ticket-less reviewer dispatch in active run

Reviewers are always ticketed; an ad-hoc reviewer dispatch bypasses the
frozen-diff sha binding. Workers (general-purpose) stay un-gated here — the
phase-end evidence gate covers them.

Not-tested: live dispatch (run-4 dogfood)
Confidence: medium (subagent_type substring match; namespaced forms tolerated)"
```

---

## Task 5: `headless-sync-dispatch-guard.sh` — block background dispatch in headless

**Files:**
- Create: `hooks/headless-sync-dispatch-guard.sh`
- Create: `hooks/test_headless_sync_dispatch_guard.py`
- Modify: `hooks/hooks.json`
- Modify: `tests/test_hooks_wiring.py`

Under `HARNESS_HEADLESS=1`, a Task/Bash call with `tool_input.run_in_background
== true` is denied (the F-6 failure mode: PM background-dispatched reviewers
then exited, orphaning them). Outside headless → allow. `&`-backgrounded Bash
is NOT covered (documented residual).

- [ ] **Step 1: Write the failing self-test**

Create `hooks/test_headless_sync_dispatch_guard.py`:

```python
#!/usr/bin/env python3
"""Self-test for headless-sync-dispatch-guard.sh."""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent / "headless-sync-dispatch-guard.sh")


def run_case(label, headless, tool_name, run_in_background, expect) -> bool:
    payload = {"tool_name": tool_name,
               "tool_input": {"run_in_background": run_in_background, "prompt": "x", "command": "x"}}
    env = os.environ.copy()
    env.pop("HARNESS_HEADLESS", None)
    if headless:
        env["HARNESS_HEADLESS"] = "1"
    result = subprocess.run(["bash", HOOK], input=json.dumps(payload),
                            capture_output=True, text=True, env=env)
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and "deny" in stdout) else "ALLOW"
    ok = actual == expect
    print(f"[{'OK  ' if ok else 'FAIL'}] {label:46s} expect={expect:5s} got={actual:5s}")
    if not ok:
        print(f"       stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


CASES = [
    ("headless + background Task", True, "Task", True, "DENY"),
    ("headless + foreground Task", True, "Task", False, "ALLOW"),
    ("headless + background Bash", True, "Bash", True, "DENY"),
    ("NOT headless + background Task", False, "Task", True, "ALLOW"),
    ("headless + no bg field Task", True, "Task", None, "ALLOW"),
]


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the self-test to verify it fails**

Run: `python3 hooks/test_headless_sync_dispatch_guard.py`
Expected: FAIL — hook file does not exist yet (`bash: ... No such file`).

- [ ] **Step 3: Write the hook**

Create `hooks/headless-sync-dispatch-guard.sh`:

```bash
#!/usr/bin/env bash
# headless-sync-dispatch-guard.sh — PreToolUse(Task|Bash)
# Under HARNESS_HEADLESS=1 the PM session must dispatch subagents SYNCHRONOUSLY:
# a background dispatch can be orphaned when the headless session exits between
# iterations (F-6, run 2). Deny run_in_background=true in headless mode.
#
# Residual: Bash backgrounding via a trailing `&` is not detected (would need
# fuzzy command parsing) — deliberately out of scope.
# Unparseable stdin → allow (fail-open repo convention).
set -euo pipefail

deny() {
  local reason="$1"
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}' \
    "${reason//\"/\\\"}"
  exit 0
}

# Only act in headless mode.
[[ "${HARNESS_HEADLESS:-}" != "1" ]] && exit 0

payload=$(cat)

bg=$(printf '%s' "$payload" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print("1" if (d.get("tool_input") or {}).get("run_in_background") is True else "0")
except Exception:
    print("err")
' 2>/dev/null || echo "err")

[[ "$bg" == "err" ]] && exit 0  # fail-open

if [[ "$bg" == "1" ]]; then
  deny "Headless mode (HARNESS_HEADLESS=1) forbids run_in_background dispatch: a backgrounded subagent is orphaned when the session exits between iterations. Dispatch synchronously."
fi

exit 0
```

- [ ] **Step 4: Run the self-test to verify it passes**

Run: `python3 hooks/test_headless_sync_dispatch_guard.py`
Expected: `5/5 passed`

- [ ] **Step 5: Wire into hooks.json**

In `hooks/hooks.json`, inside `hooks.PreToolUse`, add this entry (place it
immediately before the existing `dispatch-contract-gate.sh` Task entry):

```json
{
  "matcher": "Task|Bash",
  "hooks": [
    {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/headless-sync-dispatch-guard.sh"
    }
  ]
}
```

- [ ] **Step 6: Add the wiring test**

In `tests/test_hooks_wiring.py`, add this method to `class TestHooksJsonWiring`:

```python
    def test_headless_sync_dispatch_guard_wired(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        entry = next(
            (e for e in pre if any(
                "headless-sync-dispatch-guard.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "headless-sync-dispatch-guard.sh not wired"
        for tool in ("Task", "Bash"):
            assert tool in entry["matcher"], f"{tool} missing from matcher"
```

- [ ] **Step 7: Run wiring test + validate JSON**

Run: `python3 -m pytest tests/test_hooks_wiring.py -q && python3 -c "import json; json.load(open('hooks/hooks.json'))"`
Expected: PASS + no JSON error.

- [ ] **Step 8: Shellcheck + chmod + commit**

```bash
shellcheck -S warning hooks/headless-sync-dispatch-guard.sh
chmod +x hooks/headless-sync-dispatch-guard.sh
git add hooks/headless-sync-dispatch-guard.sh hooks/test_headless_sync_dispatch_guard.py hooks/hooks.json tests/test_hooks_wiring.py
AUTO_PILOT_MAIN_OK=1 git commit -m "feat(hook): headless-sync-dispatch-guard blocks background dispatch in headless

Deterministic guard for the F-6 orphan-reviewer failure: HARNESS_HEADLESS=1 +
run_in_background=true → deny. Enforces with code what prompt rules requested.

Not-tested: Bash trailing-& backgrounding (documented residual, out of scope)
Confidence: high"
```

---

## Task 6: Model-agnostic doc reword (§4 drift rider)

**Files:**
- Modify: `agents/pm-orchestrator.md` (and any file with "Opus 4.7 main session")

- [ ] **Step 1: Find every occurrence**

Run: `grep -rln "Opus 4.7" agents/ skills/ docs/ commands/ CLAUDE.md`
Record the list. Expected hits include `agents/pm-orchestrator.md:9` and
`skills/auto-pilot/SKILL.md:41`.

- [ ] **Step 2: Reword each occurrence**

For each hit, replace the model-specific phrase. Examples (apply the matching
pattern per file — read the line first, keep surrounding prose intact):

- `the PM (Opus 4.7 main session)` → `the PM (the main session)`
- `The PM stays in the main session (Opus 4.7)` → `The PM stays in the main session`
- `Opus 4.7 main session` → `main-session PM`

Leave worker model references (`Sonnet 4.6 (1M context)`) unchanged — still
accurate. Do NOT touch the historical model IDs in `CLAUDE.md`'s model-routing
table or memory files.

- [ ] **Step 3: Verify no stale model-as-PM phrasing remains**

Run: `grep -rn "Opus 4.7" agents/ skills/ commands/`
Expected: no output (all PM references now model-agnostic).

- [ ] **Step 4: Run doc-reference integrity**

Run: `python3 scripts/docs/check_doc_reference_integrity.py`
Expected: `doc-reference-integrity: OK (0 violations)`

- [ ] **Step 5: Commit**

```bash
git add agents/ skills/ commands/ docs/ CLAUDE.md
AUTO_PILOT_MAIN_OK=1 git commit -m "docs: model-agnostic PM phrasing (PM model is session-selected)

The main-session PM model is whatever the operator selects (Fable 5 / Opus
4.8 / ...). Hard-coded 'Opus 4.7 main session' was drift.

Confidence: high"
```

---

## Task 7: Run-4 dogfood spec (§5 live-run input)

**Files:**
- Create: `docs/specs/2026-06-10-run4-reject-and-conflict-smoke.md`

This is an INPUT document for a future live run, not code. It must be concrete
enough that the headless PM produces a guaranteed REJECT in phase 1 and a
guaranteed merge conflict in phase 2.

- [ ] **Step 1: Write the spec**

Create `docs/specs/2026-06-10-run4-reject-and-conflict-smoke.md`:

````markdown
---
type: spec
topic: run4-reject-and-conflict-smoke
manual_edit: true
---

# Run 4 — REJECT round + merge-conflict smoke

**Date**: 2026-06-10
**Status**: live-run input (proves: reviewer REJECT→fix→APPROVE loop ·
multi-contract parallel · apply_to_main conflict path · the new exit/entry
gates + headless guard live)
**Run with**: `/auto-pilot-server` headless, F-6-fixed prompts.

## Phase 1 — seeded-defect REJECT round (1 contract)

**Goal**: worker EDITS the existing `tests/test_status.py` and appends ONE
test, but the round-1 worker ticket instructs committing WITHOUT the mandatory
trailer block. Spec acceptance REQUIRES the trailer block. Reviewers must catch
the missing trailers → REJECT → round-2 adds trailers → APPROVE → merge.

Append this test:

```python
def test_worker_status_terminal_set_nonempty() -> None:
    from _status import TERMINAL
    assert len(TERMINAL) >= 1
```

**Scope files**: `tests/test_status.py` (existing — EDIT)

**Acceptance**:
- Round 1 commit deliberately omits the trailer block (`Rejected:` /
  `Confidence:` etc.) → at least one reviewer REJECTs citing missing trailers.
- Round 2 re-commit includes the full trailer block → both reviewers APPROVE.
- `python3 -m pytest -q tests/test_status.py` passes.
- Phase advances ONLY after dual APPROVE (exit gate proves it).

**Expected gate behavior**: if reviewers MISS the missing trailers, that is a
recorded reviewer-quality P1 finding (both outcomes are signal). The phase-end
exit gate still blocks advance unless both review.json are APPROVE + sha-bound.

**Verify cmd**: `python3 -m pytest -q tests/test_status.py`

## Phase 2 — merge-conflict + multi-contract parallel (2 contracts)

**Goal**: two contracts dispatched in parallel, BOTH appending a test at the
END of the SAME file `tests/test_log.py` → guaranteed textual conflict in
`apply_to_main`.

Contract A appends:

```python
def test_log_event_emits_to_stderr_a(capsys) -> None:
    from _log import event
    event("smoke.a", k="v")
    assert "smoke.a" in capsys.readouterr().err
```

Contract B appends:

```python
def test_log_event_emits_to_stderr_b(capsys) -> None:
    from _log import event
    event("smoke.b", k="v")
    assert "smoke.b" in capsys.readouterr().err
```

**Scope files**: both contracts list `tests/test_log.py` (existing — EDIT).

**Acceptance**:
- One contract merges first; the second's `apply_to_main` returns a conflict
  result (`git am --abort`, main stays clean — assert `git status --porcelain`
  empty after the abort).
- PM re-dispatches the conflicted contract rebased on the new main → it merges.
- Both tests present and passing at phase end.
- A conflict event is logged; main is never left dirty.

**Verify cmd**: `python3 -m pytest -q tests/test_log.py`

## Non-goals

No changes outside the named scope files; no new files; no refactoring.
Reviewers review normally (phase-1's REJECT is driven by the seeded ticket
instruction, not by relaxing review).

## Cleanup

The added tests are genuine smoke guards and STAY. Re-running requires removing
them first. The seeded-defect instruction lives in the run's worker ticket, not
in the committed test.
````

- [ ] **Step 2: Doc-reference integrity**

Run: `python3 scripts/docs/check_doc_reference_integrity.py`
Expected: `OK (0 violations)`.

- [ ] **Step 3: Commit**

```bash
git add docs/specs/2026-06-10-run4-reject-and-conflict-smoke.md
AUTO_PILOT_MAIN_OK=1 git commit -m "docs(spec): run-4 REJECT + merge-conflict dogfood input

Two-phase live-run input: seeded-defect REJECT round (missing trailers) +
EOF-collision merge conflict across two parallel contracts. Exercises the new
exit/entry gates and the headless guard live.

Confidence: high"
```

---

## Task 8: Full verification gate

**Files:** none (verification only)

- [ ] **Step 1: Run the complete suite**

```bash
python3 -m pytest tests/ -q
python3 -m mypy scripts/ hooks/
python3 -m ruff check scripts/ tests/ hooks/
python3 hooks/test_guard_destructive.py
python3 hooks/test_dispatch_contract_gate.py
python3 hooks/test_headless_sync_dispatch_guard.py
bash scripts/quality/check-module-size.sh
shellcheck -S warning hooks/*.sh
python3 scripts/docs/check_doc_reference_integrity.py
```
Expected: all green. `_evidence.py` and both new hooks under 500 lines;
`orchestrator.py` still ≤500 (added ~10 lines).

- [ ] **Step 2: If module-size fails on `orchestrator.py`**

If the added lines pushed `orchestrator.py` over 500, move `cmd_phase_end`'s
evidence block into a small `_evidence.gate_phase_end(state_dir) -> str | None`
helper (returns a BLOCKED message or None) and call it from `cmd_phase_end` in
2 lines. Re-run Step 1.

- [ ] **Step 3: Commit any fixups**

```bash
git add -A
AUTO_PILOT_MAIN_OK=1 git commit -m "chore: green the full gate after run-3 residual fixes

Confidence: high" || echo "nothing to fix up"
```

---

## Task 9: Live dogfood (run-4) — execute under user supervision

**Files:** none (live run)

> This task RUNS the loop; it is not a code edit. Execute only with the user
> present (headless cost + merge of real commits). The PM model is the current
> session model.

- [ ] **Step 1: Preconditions**

```bash
git status --short            # must be clean
gh api user --jq .login       # must be lyanpark2019; switch if not
python3 -m pytest tests/ -q   # green baseline
```

- [ ] **Step 2: Init + launch headless on the run-4 spec**

```bash
python3 scripts/orchestrator.py init --spec docs/specs/2026-06-10-run4-reject-and-conflict-smoke.md --force --max-workers 2
```
Then launch via `/auto-pilot-server` (the skill forks `scripts/headless-loop.py`).

- [ ] **Step 3: Observe the acceptance signals**

- Phase 1: a reviewer REJECT in round 1 (missing trailers), APPROVE in round 2.
  If no REJECT appears, record it as a reviewer-quality P1 finding — do NOT
  hand-fix; the gate behavior is the test.
- Phase 1: `phase-end --status success` only after dual APPROVE (grep the run
  log for `phase_end.evidence_failed` — there should be none on the APPROVE
  round, and the gate must have blocked any premature advance).
- Phase 2: a logged conflict event; `git status --porcelain` empty after the
  `git am --abort`; the re-dispatched contract merges; both tests pass.
- No `headless-sync-dispatch-guard` denial in the log (prompts are F-6-fixed,
  so dispatches are synchronous — a denial would mean a prompt regression).

- [ ] **Step 4: Record outcome to memory**

Update `next-session-queue.md` (or a fresh handoff memory): which loop paths are
now PROVEN (REJECT-round, merge-conflict, multi-contract, multi-phase), any new
findings, and the residuals that remain.

---

## Self-Review

**Spec coverage:**
- §1 exit gate → Tasks 1, 2, 3. ✓
- §2 entry gate fail-closed (reviewer-scoped) → Task 4. ✓
- §3 headless guard → Task 5. ✓
- §4 doc reword → Task 6. ✓
- §5 run-4 dogfood (REJECT + merge-conflict + multi-contract, one headless run) → Tasks 7, 9. ✓
- Testing requirements (pytest matrix, hook self-tests, full gate) → Tasks 1-5, 8. ✓

**Deviations from spec (intentional, recorded):**
- `_expected_agents` is NOT modified (spec already corrected): changing it would
  hang `collect_round_outcome` on worker-only collections; presence is enforced
  at the exit gate instead.
- Evidence binds via the reviewer **ticket** `diff_sha256` + recomputed
  `frozen.diff` sha (review.json has no diff-sha field — confirmed in schema).
- `cmd_phase_end` locates contract dirs via `latest_round_dirs_for_active_phase`
  (max phase-N dir), avoiding the state-phase-index ↔ dir-phase off-by-one.
- `AUTO_PILOT_SKIP_EVIDENCE=1` escape hatch added for unit tests that fabricate
  state without contract dirs — documented as test-only.

**Placeholder scan:** none. `_state.STATE_DIR` confirmed as the relative path
`.planning/auto-pilot` (resolves against CWD), so the Task 3 test isolates state
via `cwd=tmp_path` with no env override.

**Type/name consistency:** `assert_round_evidence`, `EvidenceError`,
`latest_round_dirs_for_active_phase`, `_evidence` module name, and
`AUTO_PILOT_SKIP_EVIDENCE` are used identically across Tasks 1-3 and 8.
````

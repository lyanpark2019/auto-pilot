"""Dogfood gate assertions — Tier 1 + Tier 2 acceptance checks.

Used by ``scripts/dogfood_tier1.sh`` and ``scripts/dogfood_tier2.sh`` after a
smoke spec run completes. Each assertion is a pure Python check against the
on-disk contract + git state; no claude session is spawned.

The helpers are framework-independent so they can also be called from pytest
fixtures or other ops scripts.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import _contract


class GateError(RuntimeError):
    """Raised when a dogfood gate check fails."""


@dataclass(frozen=True)
class GateReport:
    """Outcome of a tier check."""

    tier: int
    passed: bool
    failures: list[str]


def _find_contract_dirs(contracts_root: Path) -> list[Path]:
    """Return all leaf round-* dirs under .planning/auto-pilot/contracts/."""
    if not contracts_root.exists():
        return []
    out: list[Path] = []
    for iter_dir in sorted(contracts_root.glob("iter-*")):
        for phase_dir in sorted(iter_dir.glob("phase-*")):
            for contract_dir in sorted(phase_dir.glob("contract-*")):
                for round_dir in sorted(contract_dir.glob("round-*")):
                    out.append(round_dir)
    return out


def assert_phases_completed(state_path: Path, expected: int) -> list[str]:
    if not state_path.exists():
        return [f"state.json missing at {state_path}"]
    state = json.loads(state_path.read_text())
    failures: list[str] = []
    if state.get("status") != "success":
        failures.append(f"state.status = {state.get('status')!r}, expected 'success'")
    if state.get("current_phase", 0) != expected:
        failures.append(f"current_phase = {state.get('current_phase')}, expected {expected}")
    phases = state.get("phases", [])
    successes = sum(1 for p in phases if p.get("status") == "success")
    if successes != expected:
        failures.append(f"only {successes}/{expected} phases reached status=success")
    return failures


def assert_no_active_worktrees(worktrees_dir: Path) -> list[str]:
    if not worktrees_dir.exists():
        return []
    leftover = [p for p in worktrees_dir.iterdir() if p.is_dir()]
    if leftover:
        return [f"{len(leftover)} worktree(s) not reaped: {[p.name for p in leftover]}"]
    return []


def assert_contracts_signed(contracts_root: Path) -> list[str]:
    failures: list[str] = []
    for round_dir in _find_contract_dirs(contracts_root):
        contract = round_dir / "contract.json"
        sig = round_dir / "PM-SIGNATURE"
        if not contract.exists():
            failures.append(f"missing contract.json: {round_dir}")
            continue
        if not sig.exists():
            failures.append(f"missing PM-SIGNATURE: {round_dir}")
            continue
        try:
            _contract.read_contract(contract)
        except Exception as e:
            failures.append(f"contract schema invalid at {round_dir}: {e}")
            continue
        try:
            _contract.verify_pm_signature(round_dir)
        except Exception as e:
            failures.append(f"PM-SIGNATURE mismatch at {round_dir}: {e}")
    return failures


def assert_trailer_chain(repo_root: Path, expected_phases: int) -> list[str]:
    res = subprocess.run(
        ["git", "log", "--format=%H%n%B%n---END---", "-n", "20"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        return [f"git log failed: {res.stderr.strip()}"]
    text = res.stdout
    iter_trailers = set(re.findall(r"auto-pilot-iter:\s*(\S+)", text))
    phase_trailers = set(re.findall(r"auto-pilot-phase:\s*(\d+)", text))
    failures: list[str] = []
    if not iter_trailers:
        failures.append("no commits carry auto-pilot-iter trailer")
    if len(phase_trailers) < expected_phases:
        failures.append(
            f"expected {expected_phases} distinct phase trailers, found {sorted(phase_trailers)}"
        )
    return failures


def assert_no_sandbox_violations(state_dir: Path) -> list[str]:
    log = state_dir / "sandbox-violations.jsonl"
    if not log.exists():
        return []
    lines = [line for line in log.read_text().splitlines() if line.strip()]
    if lines:
        return [f"{len(lines)} sandbox violation(s) recorded"]
    return []


def _role_output_dirs(outputs: Path) -> list[Path]:
    """Enumerate one-level role dirs plus per-specialist subdirs.

    Layout (per PR1 spec):
      outputs/worker/
      outputs/codex-reviewer/
      outputs/claude-reviewer/
      outputs/specialists/<name>/        # nested one extra level
    """
    out: list[Path] = []
    if not outputs.exists():
        return out
    for role_dir in outputs.iterdir():
        if not role_dir.is_dir():
            continue
        if role_dir.name == "specialists":
            for spec_dir in role_dir.iterdir():
                if spec_dir.is_dir():
                    out.append(spec_dir)
            continue
        out.append(role_dir)
    return out


def assert_reviewer_outputs_present(contracts_root: Path) -> list[str]:
    """For each round, every role dir (including each specialist) must have
    done.marker + exit-code.txt + (review.json | status.json)."""
    failures: list[str] = []
    for round_dir in _find_contract_dirs(contracts_root):
        outputs = round_dir / "outputs"
        if not outputs.exists():
            failures.append(f"missing outputs/ at {round_dir}")
            continue
        for role_dir in _role_output_dirs(outputs):
            done = role_dir / "done.marker"
            ec = role_dir / "exit-code.txt"
            if not done.exists():
                failures.append(f"missing done.marker: {role_dir}")
            if not ec.exists():
                failures.append(f"missing exit-code.txt: {role_dir}")
            review = role_dir / "review.json"
            status = role_dir / "status.json"
            if not review.exists() and not status.exists():
                failures.append(f"missing review.json/status.json: {role_dir}")
    return failures


def run_tier1(repo_root: Path, expected_phases: int = 2) -> GateReport:
    """Tier 1: PR1 + PR2 acceptance (reviewer sandbox disabled or not yet wired)."""
    state_dir = repo_root / ".planning" / "auto-pilot"
    failures: list[str] = []
    failures += assert_phases_completed(state_dir / "state.json", expected_phases)
    failures += assert_no_active_worktrees(state_dir / "worktrees")
    failures += assert_contracts_signed(state_dir / "contracts")
    failures += assert_trailer_chain(repo_root, expected_phases)
    return GateReport(tier=1, passed=not failures, failures=failures)


def run_tier2(repo_root: Path, expected_phases: int = 2) -> GateReport:
    """Tier 2: Tier 1 plus PR3 reviewer sandbox acceptance."""
    tier1 = run_tier1(repo_root, expected_phases)
    failures = list(tier1.failures)
    state_dir = repo_root / ".planning" / "auto-pilot"
    failures += assert_no_sandbox_violations(state_dir)
    failures += assert_reviewer_outputs_present(state_dir / "contracts")
    return GateReport(tier=2, passed=not failures, failures=failures)


def _main() -> int:
    import argparse

    p = argparse.ArgumentParser(prog="auto-pilot-dogfood-gate")
    p.add_argument("--tier", type=int, choices=[1, 2], required=True)
    p.add_argument("--repo-root", type=Path, default=Path.cwd())
    p.add_argument("--phases", type=int, default=2)
    args = p.parse_args()
    report = (run_tier1 if args.tier == 1 else run_tier2)(args.repo_root, args.phases)
    payload = {"tier": report.tier, "passed": report.passed, "failures": report.failures}
    print(json.dumps(payload, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(_main())

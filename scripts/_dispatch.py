"""PM-owned dispatch primitives for auto-pilot subagent ticket protocol.

Enforcement layers for contract integrity (ⓓ-7②, 2026-06 round-2 W2):
  Layer 1 — _contract.validate (schema validation on every read/write)
  Layer 2 — prepare_subagent_ticket refuses dispatch when the
             dispatch-contract-check artifact is absent or stale (this file)
  Layer 3 — PreToolUse(Task) hook (contract γ builds it; the artifact format
             is documented in dispatch_contract_check() below)

Preflight gate (ⓓ-9, 2026-06 round-2 W2):
  prepare_subagent_ticket also checks for a valid preflight artifact under
  .planning/auto-pilot/preflight/phase-<N>.json.  Four rejection paths:
  missing file, TTL > 900 s, wrong phase key, head_sha != current HEAD.
  Interactive wiring of pm_preflight.sh via PreToolUse(Bash) is γ's hook
  contract; if γ's wiring lands as prompt-gated only that is recorded as
  residual risk (see module docstring).

Residual risk: interactive review dispatch (Agent tool) bypasses this gate
  entirely — the hook path is the only enforcement there.  Mitigation:
  codex exec Bash timeout + Task deadline.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time as _time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import jsonschema

import _contract

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
TICKET_SCHEMA_PATH = SCHEMAS_DIR / "ticket.schema.json"
_VALID_ROLES = {"worker", "codex-reviewer", "claude-reviewer",
                "tdd-enforcer", "security-reviewer", "tech-critic-lead"}

PREFLIGHT_TTL_SEC = 900  # 15 minutes

_TICKET_VALIDATOR: jsonschema.Draft202012Validator | None = None


def _validator() -> jsonschema.Draft202012Validator:
    global _TICKET_VALIDATOR
    if _TICKET_VALIDATOR is None:
        schema = json.loads(TICKET_SCHEMA_PATH.read_text())
        _TICKET_VALIDATOR = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
    return _TICKET_VALIDATOR


def _check_contract_check_artifact(contract_dir: Path) -> None:
    """Layer-2 enforcement: refuse dispatch when contract-check artifact is absent
    or its contract_sha256 does not match the current contract file.

    Raises ContractCheckMissing with a descriptive message.
    """
    artifact_path = contract_dir / "contract-check.json"
    if not artifact_path.exists():
        raise ContractCheckMissing(
            f"contract-check artifact missing: {artifact_path}; "
            "run `orchestrator.py dispatch-contract-check --contract <path>` first"
        )
    artifact = json.loads(artifact_path.read_text())
    if artifact.get("result") != "pass":
        raise ContractCheckMissing(
            f"contract-check artifact result is not 'pass': {artifact.get('result')!r}"
        )
    contract_path = contract_dir / "contract.json"
    actual_sha = _contract._sha256(contract_path.read_bytes())
    recorded_sha = artifact.get("contract_sha256", "")
    if actual_sha != recorded_sha:
        raise ContractCheckMissing(
            f"contract file modified since last dispatch-contract-check "
            f"(expected={recorded_sha!r}, actual={actual_sha!r})"
        )


def _check_preflight_artifact(contract_dir: Path, phase: int) -> None:
    """Preflight gate (ⓓ-9): reject dispatch when preflight is absent, stale,
    wrong-phase, or the recorded head_sha does not match current HEAD.

    The preflight artifact lives at:
      .planning/auto-pilot/preflight/phase-<N>.json
    relative to the repo root (two parents above contract_dir structure, or
    derived from contract_dir / ".." traversal — we use the repo root heuristic:
    walk up from contract_dir until a .git or .planning dir is found, then
    anchor to <repo_root>/.planning/auto-pilot/preflight/phase-<N>.json).

    Raises PreflightError with a descriptive message.
    """
    # Locate repo root: walk up from contract_dir
    candidate = contract_dir
    repo_root: Path | None = None
    for _ in range(20):  # guard against infinite loops
        if (candidate / ".git").exists() or (candidate / ".planning").exists():
            repo_root = candidate
            break
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    if repo_root is None:
        raise PreflightError(
            f"Cannot locate repo root from contract_dir={contract_dir}; "
            "preflight check skipped but gate requires it"
        )

    preflight_path = repo_root / ".planning" / "auto-pilot" / "preflight" / f"phase-{phase}.json"
    if not preflight_path.exists():
        raise PreflightError(
            f"Preflight artifact missing: {preflight_path}; "
            "run `bash scripts/pm_preflight.sh` first"
        )

    preflight = json.loads(preflight_path.read_text())

    # TTL check
    generated_ts_str = preflight.get("generated_ts", "")
    try:
        generated_dt = datetime.fromisoformat(generated_ts_str)
        age_sec = (datetime.now(timezone.utc) - generated_dt).total_seconds()
        if age_sec > PREFLIGHT_TTL_SEC:
            raise PreflightError(
                f"Preflight artifact too old: {age_sec:.0f}s > TTL {PREFLIGHT_TTL_SEC}s; "
                f"re-run `bash scripts/pm_preflight.sh`"
            )
    except (ValueError, TypeError) as exc:
        raise PreflightError(
            f"Preflight artifact has invalid generated_ts: {generated_ts_str!r}"
        ) from exc

    # Phase key check
    artifact_phase = preflight.get("phase")
    if artifact_phase != phase:
        raise PreflightError(
            f"Preflight artifact phase mismatch: artifact.phase={artifact_phase!r}, "
            f"expected {phase}"
        )

    # HEAD sha check
    try:
        current_head = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        # If git fails, skip HEAD check (non-git environment)
        return
    artifact_head = preflight.get("head_sha", "")
    if current_head != artifact_head:
        raise PreflightError(
            f"Preflight head_sha mismatch: artifact={artifact_head!r}, "
            f"current HEAD={current_head!r}; re-run `bash scripts/pm_preflight.sh`"
        )


def prepare_subagent_ticket(
    *,
    contract_dir: Path,
    worktree: Path,
    subagent_role: str,
    diff_path: Path | None = None,
    skip_preflight: bool = False,
    skip_contract_check: bool = False,
) -> Path:
    """PM-side validation. Writes a signed ticket under <contract_dir>/tickets/<role>.json.

    Validates contract + PM-SIGNATURE + snapshots BEFORE writing the ticket.
    Also enforces:
      - Layer-2 contract-check artifact (ⓓ-7②): ``ContractCheckMissing`` on failure
        (disable with ``skip_contract_check=True`` for tests / initial bootstrap).
      - Preflight artifact (ⓓ-9): ``PreflightError`` on failure
        (disable with ``skip_preflight=True`` for tests / non-interactive).
    Returns the ticket path.

    Raises:
        ValueError on invalid role.
        ContractValidationError / SnapshotMismatchError / PMSignatureMismatchError
            on contract integrity failures.
        ContractCheckMissing when the contract-check artifact is absent or stale.
        PreflightError when the preflight artifact is missing / stale / wrong HEAD.
    """
    if subagent_role not in _VALID_ROLES:
        raise ValueError(f"unknown subagent_role: {subagent_role!r}; allowed: {sorted(_VALID_ROLES)}")

    _contract.verify_pm_signature(contract_dir)
    _contract.verify_snapshots(contract_dir)
    contract = _contract.read_contract(contract_dir / "contract.json")

    if not skip_contract_check:
        _check_contract_check_artifact(contract_dir)

    if not skip_preflight:
        phase = contract.get("phase", 0)
        _check_preflight_artifact(contract_dir, phase)

    output_dir = contract_dir / "outputs" / subagent_role
    output_dir.mkdir(parents=True, exist_ok=True)

    helper_abspath = str((Path(__file__).resolve().parent / "_subagent_helpers.py"))

    body: dict[str, Any] = {
        "schema_version":  1,
        "contract_id":     contract["id"],
        "base_sha":        contract["snapshot_shas"]["base_sha"],
        "contract_dir":    str(contract_dir.resolve()),
        "worktree":        str(worktree.resolve()),
        "subagent_role":   subagent_role,
        "output_dir":      str(output_dir.resolve()),
        "helper_abspath":  helper_abspath,
        "diff_path":       str(diff_path.resolve()) if diff_path else None,
        "diff_sha256":     None,
        "boot_ok_at":      datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    if diff_path:
        body["diff_sha256"] = _contract._sha256(diff_path.read_bytes())
    body["ticket_sha"] = _compute_ticket_sha(body)

    _validator().validate(body)

    tickets_dir = contract_dir / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    ticket_path = tickets_dir / f"{subagent_role}.json"
    _contract.atomic_write_text(ticket_path, json.dumps(body, indent=2, sort_keys=True) + "\n")
    return ticket_path


def _compute_ticket_sha(body_without_sha: dict[str, Any]) -> str:
    """Deterministic sha256 of canonicalized ticket body sans the ticket_sha field."""
    canonical = json.dumps(body_without_sha, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def freeze_diff_for_review(worktree: Path, base_sha: str, contract_dir: Path) -> Path:
    """PM-side: capture worker HEAD diff against base_sha, write to review-input/ with sha."""
    review_input = contract_dir / "review-input"
    review_input.mkdir(parents=True, exist_ok=True)
    diff_bytes = subprocess.check_output(
        ["git", "-C", str(worktree), "diff", base_sha, "HEAD"]
    )
    diff_path = review_input / "frozen.diff"
    diff_path.write_bytes(diff_bytes)
    sha_path = review_input / "frozen.diff.sha256"
    sha_path.write_text(_contract._sha256(diff_bytes) + "\n")
    return diff_path


REVIEW_SCHEMA_PATH = SCHEMAS_DIR / "review.schema.json"
_REVIEW_VALIDATOR: jsonschema.Draft202012Validator | None = None


def _review_validator() -> jsonschema.Draft202012Validator:
    global _REVIEW_VALIDATOR
    if _REVIEW_VALIDATOR is None:
        schema = json.loads(REVIEW_SCHEMA_PATH.read_text())
        _REVIEW_VALIDATOR = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
    return _REVIEW_VALIDATOR


class MalformedReviewError(Exception):
    """Raised when review.json fails schema validation."""


class RoundCollectTimeout(Exception):
    """Raised when an expected agent's done.marker never appears within the timeout."""


class ContractCheckMissing(Exception):
    """Raised when the contract-check artifact is absent or contract sha does not match.

    Artifact format (written by ``dispatch_contract_check``):
      {
        "contract_sha256": "<hex>",
        "checked_at": "<iso8601>",
        "schema_version": <int>,
        "result": "pass"
      }
    Layer 3 (PreToolUse hook built by contract γ) reads the same artifact.
    """


class PreflightError(Exception):
    """Raised when the preflight artifact is missing, stale, wrong-phase, or wrong HEAD."""


def read_review(path: Path) -> dict[str, Any]:
    """Read + schema-validate a review.json. Raises MalformedReviewError on bad shape."""
    data = json.loads(path.read_text())
    errors = sorted(_review_validator().iter_errors(data), key=lambda e: e.path)
    if errors:
        raise MalformedReviewError(
            "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        )
    return cast(dict[str, Any], data)


@dataclass
class RoundOutcome:
    worker_exit_code: int | None
    worker_status: dict[str, Any] | None
    codex_verdict: str | None
    codex_review:  dict[str, Any] | None
    claude_verdict: str | None
    claude_review:  dict[str, Any] | None
    specialists:    dict[str, dict[str, Any]]


def collect_round_outcome(contract_dir: Path, timeout_per_agent_sec: int) -> RoundOutcome:
    """Wait for done.marker per expected agent, read exit-code + payload, schema-validate.

    PM does NOT read Agent return text for control flow — only filesystem state.
    """
    outputs = contract_dir / "outputs"
    expected = []
    if (outputs / "worker").exists():
        expected.append("worker")
    if (outputs / "codex-reviewer").exists():
        expected.append("codex-reviewer")
    if (outputs / "claude-reviewer").exists():
        expected.append("claude-reviewer")

    deadlines = {name: _time.time() + timeout_per_agent_sec for name in expected}
    while expected:
        for name in list(expected):
            marker = outputs / name / "done.marker"
            if marker.exists():
                expected.remove(name)
                continue
            if _time.time() > deadlines[name]:
                raise RoundCollectTimeout(f"no done.marker for {name}")
        _time.sleep(0.05)

    def _exit_code(name: str) -> int | None:
        p = outputs / name / "exit-code.txt"
        return int(p.read_text().strip()) if p.exists() else None

    def _read_status(name: str) -> dict[str, Any] | None:
        p = outputs / name / "status.json"
        return json.loads(p.read_text()) if p.exists() else None

    def _read_review(name: str) -> dict[str, Any] | None:
        p = outputs / name / "review.json"
        return read_review(p) if p.exists() else None

    codex_review = _read_review("codex-reviewer")
    claude_review = _read_review("claude-reviewer")
    specialists: dict[str, dict[str, Any]] = {}
    specialists_dir = outputs / "specialists"
    if specialists_dir.exists():
        for sub in specialists_dir.iterdir():
            if sub.is_dir() and (sub / "review.json").exists():
                specialists[sub.name] = read_review(sub / "review.json")

    return RoundOutcome(
        worker_exit_code=_exit_code("worker"),
        worker_status=_read_status("worker"),
        codex_verdict=(codex_review or {}).get("verdict"),
        codex_review=codex_review,
        claude_verdict=(claude_review or {}).get("verdict"),
        claude_review=claude_review,
        specialists=specialists,
    )


class ScopeViolation(Exception):
    """Raised when reviewer left repo/worktree in dirty state."""


def assert_reviewer_was_scoped(repo_root: Path, worktree: Path,
                                allowed_output_dir: Path) -> None:
    """Verify that repo_root and worktree are both clean (git status --porcelain empty).

    Reviewer is only allowed to write inside allowed_output_dir. Any other write
    surfaces as a dirty file in repo_root or worktree.
    """
    for path in (repo_root, worktree):
        if not (path / ".git").exists() and path.exists() and not (path.is_dir()):
            continue
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=True,
        )
        if result.stdout.strip():
            raise ScopeViolation(
                f"reviewer left {path} dirty (allowed_output_dir={allowed_output_dir}): {result.stdout}"
            )

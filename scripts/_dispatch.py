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
from typing import cast

import jsonschema

import _contract
import _contract_check
from _log import event

# Matches _worktree.py timeout budget convention.
_GIT_QUICK_TIMEOUT = 30  # rev-parse, status plumbing
_GIT_TREE_TIMEOUT = 60   # diff across potentially large trees

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
TICKET_SCHEMA_PATH = SCHEMAS_DIR / "ticket.schema.json"
_VALID_ROLES = {"worker", "codex-reviewer", "claude-reviewer"}
# review-gatekeeper and tech-critic-lead are inline-only agents (tools: Read, Grep, Glob, Bash;
# no Write) — they return inline YAML and cannot produce ticket-boot artifacts
# (done.marker / exit-code.txt / review.json).  They must never appear here.

_TICKET_VALIDATOR: jsonschema.Draft202012Validator | None = None
JsonObject = dict[str, object]


def _as_str(value: object) -> str:
    if isinstance(value, str):
        return value
    raise ValueError(f"expected string JSON value, got {type(value).__name__}")


def _as_int(value: object) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise ValueError(f"expected integer JSON value, got {type(value).__name__}")


def _as_object(value: object) -> JsonObject:
    if isinstance(value, dict):
        return cast(JsonObject, value)
    raise ValueError(f"expected object JSON value, got {type(value).__name__}")


def _optional_str(value: object | None) -> str | None:
    return value if isinstance(value, str) else None


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
    try:
        artifact = json.loads(artifact_path.read_text())
        _contract_check.assert_artifact_fresh(contract_dir, artifact)
    except (OSError, json.JSONDecodeError, _contract_check.ContractCheckError) as exc:
        raise ContractCheckMissing(str(exc)) from exc


def _locate_repo_root(contract_dir: Path) -> Path:
    """Walk up from contract_dir until .git or .planning is found.

    Raises PreflightError if neither anchor is found within 20 levels.
    """
    candidate = contract_dir
    for _ in range(20):
        if (candidate / ".git").exists() or (candidate / ".planning").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    raise PreflightError(
        f"Cannot locate repo root from contract_dir={contract_dir}; "
        "preflight check skipped but gate requires it"
    )


def _check_preflight_ttl(preflight: JsonObject) -> None:
    """Raise PreflightError if preflight artifact is expired or has invalid timestamp."""
    import _config  # lazy: avoid eager _config import in the dispatch hot path
    ttl_sec = _config.preflight_ttl_sec()
    generated_ts_str = _as_str(preflight.get("generated_ts", ""))
    try:
        generated_dt = datetime.fromisoformat(generated_ts_str)
        age_sec = (datetime.now(timezone.utc) - generated_dt).total_seconds()
        if age_sec > ttl_sec:
            raise PreflightError(
                f"Preflight artifact too old: {age_sec:.0f}s > TTL {ttl_sec}s; "
                f"re-run `bash scripts/pm_preflight.sh`"
            )
    except (ValueError, TypeError) as exc:
        raise PreflightError(
            f"Preflight artifact has invalid generated_ts: {generated_ts_str!r}"
        ) from exc


def _is_genuine_non_git(repo_root: Path) -> bool:
    """True only for a genuinely-not-a-git context (no work tree, or unborn HEAD).

    Used to keep the legitimate non-git skip in :func:`_check_preflight_head_sha`
    while a transient git failure (lock/corruption/wrong cwd) is treated as a
    gate failure rather than failing open.
    """
    try:
        inside = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=_GIT_QUICK_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return True
    head = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "--verify", "-q", "HEAD"],
        capture_output=True, text=True, timeout=_GIT_QUICK_TIMEOUT,
    )
    return head.returncode != 0


def _check_preflight_head_sha(preflight: JsonObject, repo_root: Path) -> None:
    """Raise PreflightError if preflight head_sha does not match current HEAD.

    Silently skips ONLY on git timeout or a genuinely-non-git context (no work
    tree, or unborn HEAD). Any other non-zero git exit (transient lock,
    corruption, wrong cwd) is treated as a gate failure — fail closed, not open.
    """
    start = _time.monotonic()
    try:
        current_head = subprocess.check_output(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            text=True, stderr=subprocess.DEVNULL,
            timeout=_GIT_QUICK_TIMEOUT,
        ).strip()
        event("dispatch.git_rev_parse", duration_ms=int((_time.monotonic() - start) * 1000))
    except subprocess.TimeoutExpired:
        sys.stderr.write(f"_dispatch: git rev-parse timed out (>{_GIT_QUICK_TIMEOUT}s), skipping HEAD check\n")
        return
    except subprocess.CalledProcessError as exc:
        if _is_genuine_non_git(repo_root):
            return
        sys.stderr.write(
            f"_dispatch: git rev-parse HEAD failed in a git repo (exit {exc.returncode}); "
            "treating preflight HEAD check as a gate failure\n"
        )
        raise PreflightError(
            f"Preflight HEAD check failed: git rev-parse HEAD errored (exit {exc.returncode}) "
            f"in repo_root={repo_root}; resolve the git state and re-run `bash scripts/pm_preflight.sh`"
        ) from exc
    artifact_head = preflight.get("head_sha", "")
    if current_head != artifact_head:
        raise PreflightError(
            f"Preflight head_sha mismatch: artifact={artifact_head!r}, "
            f"current HEAD={current_head!r}; re-run `bash scripts/pm_preflight.sh`"
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
    repo_root = _locate_repo_root(contract_dir)
    preflight_path = repo_root / ".planning" / "auto-pilot" / "preflight" / f"phase-{phase}.json"
    if not preflight_path.exists():
        raise PreflightError(
            f"Preflight artifact missing: {preflight_path}; "
            "run `bash scripts/pm_preflight.sh` first"
        )
    preflight = json.loads(preflight_path.read_text())
    _check_preflight_ttl(preflight)
    artifact_phase = preflight.get("phase")
    if artifact_phase != phase:
        raise PreflightError(
            f"Preflight artifact phase mismatch: artifact.phase={artifact_phase!r}, "
            f"expected {phase}"
        )
    _check_preflight_head_sha(preflight, repo_root)


def _validate_ticket_inputs(subagent_role: str, contract_dir: Path) -> JsonObject:
    if subagent_role not in _VALID_ROLES:
        raise ValueError(f"unknown subagent_role: {subagent_role!r}; allowed: {sorted(_VALID_ROLES)}")
    _contract.verify_pm_signature(contract_dir)
    _contract.verify_snapshots(contract_dir)
    return _contract.read_contract(contract_dir / "contract.json")


def _enforce_ticket_gates(
    contract_dir: Path,
    contract: JsonObject,
    *,
    skip_preflight: bool,
    skip_contract_check: bool,
) -> None:
    if not skip_contract_check:
        _check_contract_check_artifact(contract_dir)
    if not skip_preflight:
        _check_preflight_artifact(contract_dir, _as_int(contract.get("phase", 0)))


def _ticket_body(
    *,
    contract_dir: Path,
    worktree: Path,
    subagent_role: str,
    output_dir: Path,
    contract: JsonObject,
    diff_path: Path | None,
) -> JsonObject:
    snapshots = _as_object(contract["snapshot_shas"])
    body: JsonObject = {
        "schema_version": 1,
        "contract_id": _as_str(contract["id"]),
        "base_sha": _as_str(snapshots["base_sha"]),
        "contract_dir": str(contract_dir.resolve()),
        "worktree": str(worktree.resolve()),
        "subagent_role": subagent_role,
        "output_dir": str(output_dir.resolve()),
        "helper_abspath": str(Path(__file__).resolve().parent / "_subagent_helpers.py"),
        "diff_path": str(diff_path.resolve()) if diff_path else None,
        "diff_sha256": _contract._sha256(diff_path.read_bytes()) if diff_path else None,
        "boot_ok_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    body["ticket_sha"] = _compute_ticket_sha(body)
    return body


def _write_ticket(contract_dir: Path, subagent_role: str, body: JsonObject) -> Path:
    _validator().validate(body)
    tickets_dir = contract_dir / "tickets"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    ticket_path = tickets_dir / f"{subagent_role}.json"
    _contract.atomic_write_text(ticket_path, json.dumps(body, indent=2, sort_keys=True) + "\n")
    return ticket_path


def prepare_subagent_ticket(
    *,
    contract_dir: Path,
    worktree: Path,
    subagent_role: str,
    diff_path: Path | None = None,
    skip_preflight: bool = False,
    skip_contract_check: bool = False,
) -> Path:
    """PM-side validation. Writes a signed ticket under <contract_dir>/tickets/<role>.json."""
    contract = _validate_ticket_inputs(subagent_role, contract_dir)
    _enforce_ticket_gates(
        contract_dir,
        contract,
        skip_preflight=skip_preflight,
        skip_contract_check=skip_contract_check,
    )
    output_dir = contract_dir / "outputs" / subagent_role
    output_dir.mkdir(parents=True, exist_ok=True)
    body = _ticket_body(
        contract_dir=contract_dir,
        worktree=worktree,
        subagent_role=subagent_role,
        output_dir=output_dir,
        contract=contract,
        diff_path=diff_path,
    )
    return _write_ticket(contract_dir, subagent_role, body)


def _compute_ticket_sha(body_without_sha: JsonObject) -> str:
    """Deterministic sha256 of canonicalized ticket body sans the ticket_sha field."""
    canonical = json.dumps(body_without_sha, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def freeze_diff_for_review(worktree: Path, base_sha: str, contract_dir: Path) -> Path:
    """PM-side: capture worker HEAD diff against base_sha, write to review-input/ with sha."""
    review_input = contract_dir / "review-input"
    review_input.mkdir(parents=True, exist_ok=True)
    start = _time.monotonic()
    diff_bytes = subprocess.check_output(
        ["git", "-C", str(worktree), "diff", base_sha, "HEAD"],
        timeout=_GIT_TREE_TIMEOUT,
    )
    event("dispatch.git_diff", duration_ms=int((_time.monotonic() - start) * 1000), bytes=len(diff_bytes))
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


def read_review(path: Path) -> JsonObject:
    """Read + schema-validate a review.json. Raises MalformedReviewError on bad shape."""
    data = json.loads(path.read_text())
    errors = sorted(_review_validator().iter_errors(data), key=lambda e: e.path)
    if errors:
        raise MalformedReviewError(
            "; ".join(f"{list(e.absolute_path)}: {e.message}" for e in errors)
        )
    return cast(JsonObject, data)


@dataclass
class RoundOutcome:
    """Represent RoundOutcome data for this module."""
    worker_exit_code: int | None
    worker_status: JsonObject | None
    codex_verdict: str | None
    codex_review:  JsonObject | None
    claude_verdict: str | None
    claude_review:  JsonObject | None
    specialists:    dict[str, JsonObject]


def _expected_agents(outputs: Path) -> list[str]:
    return [
        name for name in ("worker", "codex-reviewer", "claude-reviewer")
        if (outputs / name).exists()
    ]


def _wait_for_markers(outputs: Path, expected: list[str], timeout_per_agent_sec: int) -> None:
    deadlines = {name: _time.time() + timeout_per_agent_sec for name in expected}
    pending = set(expected)
    while pending:
        for name in list(pending):
            if (outputs / name / "done.marker").exists():
                pending.remove(name)
                continue
            if _time.time() > deadlines[name]:
                raise RoundCollectTimeout(f"no done.marker for {name}")
        _time.sleep(0.05)


def _exit_code(outputs: Path, name: str) -> int | None:
    p = outputs / name / "exit-code.txt"
    return int(p.read_text().strip()) if p.exists() else None


def _read_status(outputs: Path, name: str) -> JsonObject | None:
    p = outputs / name / "status.json"
    return cast(JsonObject, json.loads(p.read_text())) if p.exists() else None


def _read_agent_review(outputs: Path, name: str) -> JsonObject | None:
    p = outputs / name / "review.json"
    return read_review(p) if p.exists() else None


def _read_specialists(outputs: Path) -> dict[str, JsonObject]:
    specialists: dict[str, JsonObject] = {}
    specialists_dir = outputs / "specialists"
    if not specialists_dir.exists():
        return specialists
    for sub in specialists_dir.iterdir():
        if sub.is_dir() and (sub / "review.json").exists():
            specialists[sub.name] = read_review(sub / "review.json")
    return specialists


def collect_round_outcome(contract_dir: Path, timeout_per_agent_sec: int) -> RoundOutcome:
    """Wait for done.marker per expected agent, read exit-code + payload, schema-validate."""
    outputs = contract_dir / "outputs"
    _wait_for_markers(outputs, _expected_agents(outputs), timeout_per_agent_sec)
    codex_review = _read_agent_review(outputs, "codex-reviewer")
    claude_review = _read_agent_review(outputs, "claude-reviewer")
    return RoundOutcome(
        worker_exit_code=_exit_code(outputs, "worker"),
        worker_status=_read_status(outputs, "worker"),
        codex_verdict=_optional_str((codex_review or {}).get("verdict")),
        codex_review=codex_review,
        claude_verdict=_optional_str((claude_review or {}).get("verdict")),
        claude_review=claude_review,
        specialists=_read_specialists(outputs),
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
        start = _time.monotonic()
        result = subprocess.run(
            ["git", "-C", str(path), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True, text=True, check=True,
            timeout=_GIT_QUICK_TIMEOUT,
        )
        event("dispatch.git_status", duration_ms=int((_time.monotonic() - start) * 1000), path=str(path))
        if result.stdout.strip():
            raise ScopeViolation(
                f"reviewer left {path} dirty (allowed_output_dir={allowed_output_dir}): {result.stdout}"
            )

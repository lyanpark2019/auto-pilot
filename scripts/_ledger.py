"""Routing ledger IO, schema validation, and record derivation.

Ledger format: YAML, schema schemas/routing-ledger.schema.json (schema_version: 1).
Per-project path: <project_root>/.claude/routing/ledger.yaml.

Design note: this module is intentionally free of orchestrator.py state; it
operates on paths passed explicitly so callers can test with tmp_path fixtures.

Rule engine (evaluate_rebalance) lives in _rebalance.py and is re-exported
here so existing callers (orchestrator.py, tests) import from one place.
"""
from __future__ import annotations

import fcntl
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml

import _contract
import _evidence
from _rebalance import evaluate_rebalance, _utc_now_iso  # re-export + S3 dedup

__all__ = [
    "LedgerError",
    "load_ledger",
    "validate_ledger",
    "save_ledger",
    "build_record_from_round_dirs",
    "append_phase_records",
    "ledger_transaction",
    "evaluate_rebalance",
]

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"
_LEDGER_SCHEMA_PATH = SCHEMAS_DIR / "routing-ledger.schema.json"

_LEDGER_VALIDATOR: Any = None  # jsonschema.Draft202012Validator, lazy-loaded

# Default field values used when contract.json lacks explicit fields.
_DEFAULT_ROLE = "worker-primary"
_DEFAULT_TASK_CLASS = "feature-multi-file"
_DEFAULT_MODEL = "sonnet"

# Outcome derivation: a REJECT is "real" when it carries at least one finding
# with severity P0 or P1. A REJECT with only P2 (or no findings) counts as
# rejects_false. This is an approximation: a reviewer who notes a P0 inline
# without using verdict=REJECT would not be counted here. Callers must not
# treat rejects_real as a precise defect count.
_REAL_SEVERITIES = frozenset({"P0", "P1"})


class LedgerError(Exception):
    """Malformed YAML, schema violation, or IO issue with the ledger."""


def _ledger_validator() -> Any:
    # Lazy-load so jsonschema import is deferred; avoids cost on non-validation paths.
    global _LEDGER_VALIDATOR
    if _LEDGER_VALIDATOR is None:
        import jsonschema
        schema = json.loads(_LEDGER_SCHEMA_PATH.read_text())
        _LEDGER_VALIDATOR = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
    return _LEDGER_VALIDATOR


def _fresh_skeleton() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "assignments": {},
        "records": [],
        "rebalance_log": [],
    }


def load_ledger(path: Path) -> dict[str, Any]:
    """Load the ledger YAML at path.

    Returns a fresh skeleton dict when the file does not exist (first run).
    Raises LedgerError when the file is present but unparseable.
    """
    if not path.exists():
        return _fresh_skeleton()
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise LedgerError(f"{path}: YAML parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise LedgerError(
            f"{path}: expected a YAML mapping, got {type(data).__name__}"
        )
    return data


def validate_ledger(data: dict[str, Any]) -> None:
    """Validate data against schemas/routing-ledger.schema.json.

    Raises LedgerError on any schema violation.
    """
    validator = _ledger_validator()
    errors = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errors:
        msg = "; ".join(
            f"{list(e.absolute_path)}: {e.message}" for e in errors
        )
        raise LedgerError(msg)


def save_ledger(path: Path, data: dict[str, Any]) -> None:
    """Validate data, then atomically write as YAML to path.

    Uses _contract.atomic_write_text for the same durability guarantees as
    contract.json writes (tempfile + fsync + rename + dir fsync).
    Raises LedgerError on schema violation; OSError on IO failure.
    """
    validate_ledger(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    _contract.atomic_write_text(path, text)


class LedgerTxn:
    """Handle yielded by ledger_transaction().

    `.ledger` is the dict loaded via load_ledger() under the held exclusive lock.
    Call `.commit()` to persist it (via save_ledger, which validates) on context
    exit; without commit nothing is written.
    """

    def __init__(self) -> None:
        self.ledger: dict[str, Any] = {}
        self._committed: bool = False

    def commit(self) -> None:
        """Mark the transaction for write on context exit."""
        self._committed = True


@contextmanager
def ledger_transaction(ledger_path: Path) -> Iterator[LedgerTxn]:
    """Exclusive-lock context manager spanning load → mutate → save.

    Lock file: ``<ledger_path>.lock`` (sibling of the YAML file).
    The lock is acquired before load_ledger and released after save_ledger
    (or after the body raises), preventing concurrent lost-update between
    cmd_phase_end auto-append and manual ledger-append/rebalance callers.

    Usage::

        with ledger_transaction(ledger_path) as txn:
            txn.ledger["assignments"]["worker-primary"] = {"model": "opus"}
            txn.commit()   # without this, nothing is written
    """
    lock_path = ledger_path.with_suffix(ledger_path.suffix + ".lock")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    fd = lock_path.open("r+")
    txn = LedgerTxn()
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        txn.ledger = load_ledger(ledger_path)
        yield txn
        if txn._committed:
            save_ledger(ledger_path, txn.ledger)
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()


def _read_review_json(path: Path) -> dict[str, Any]:
    # Returns {} on any failure so evidence collection never crashes on partial output.
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _has_real_finding(review: dict[str, Any]) -> bool:
    # P0/P1 finding = real reject; P2-only or empty = false reject.
    findings = review.get("findings") or []
    return any(
        isinstance(f, dict) and f.get("severity") in _REAL_SEVERITIES
        for f in findings
    )


def _has_p0_finding(review: dict[str, Any]) -> bool:
    # F4: P0 finding in any review (even APPROVE verdict) counts as p0_escaped.
    findings = review.get("findings") or []
    return any(
        isinstance(f, dict) and f.get("severity") == "P0"
        for f in findings
    )


def _count_outcome_fields(
    round_dirs: list[Path],
) -> tuple[int, int, int, bool, bool]:
    # Returns (rejects_real, rejects_false, review_rounds, abstained_final, p0_escaped).
    # Iterates ALL rounds so F3/F4 multi-round aggregation is correct.
    # Approximation: only P0s in review.json findings are detected; verbal P0s are not.
    rejects_real = 0
    rejects_false = 0
    abstained_final = False
    p0_escaped = False

    for i, round_dir in enumerate(round_dirs):
        is_final = i == len(round_dirs) - 1
        outputs = round_dir / "outputs"
        for role in ("claude-reviewer", "codex-reviewer"):
            review_path = outputs / role / "review.json"
            if not review_path.exists():
                continue
            review = _read_review_json(review_path)
            verdict = review.get("verdict")
            if verdict == "REJECT":
                if _has_real_finding(review):
                    rejects_real += 1
                else:
                    rejects_false += 1
            # F4: auto-derive p0_escaped from any P0 finding in any round.
            if _has_p0_finding(review):
                p0_escaped = True
            if is_final and role == "codex-reviewer" and verdict == "ABSTAIN":
                abstained_final = True

    return rejects_real, rejects_false, len(round_dirs), abstained_final, p0_escaped


def _read_contract_json(round_dir: Path) -> dict[str, Any]:
    # Read contract.json from the given round dir; return {} on any failure.
    contract_path = round_dir / "contract.json"
    if not contract_path.exists():
        return {}
    try:
        data = json.loads(contract_path.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _gates_first_try(
    round_dirs: list[Path],
) -> tuple[bool, bool]:
    # Reads outputs/worker/status.json from the FIRST round dir for a direct bool.
    # When status.json is absent OR unreadable, returns (False, True): absence of
    # evidence must not credit a first-try pass (conservative by design).
    # was_inferred=True signals the caller to add a "gates_first_try inferred" note.
    if round_dirs:
        worker_status = round_dirs[0] / "outputs" / "worker" / "status.json"
        if worker_status.exists():
            try:
                status = json.loads(worker_status.read_text())
                val = status.get("gates_first_try")
                if isinstance(val, bool):
                    return val, False
            except (json.JSONDecodeError, OSError):
                pass
    # Fallback: no readable status.json → False (conservative; do not credit without evidence).
    return False, True


def build_record_from_round_dirs(
    contract_dir: Path,
    round_dirs: list[Path],
) -> dict[str, Any]:
    """Derive one ledger record from the evidence artifacts for a contract.

    Fields derived from evidence (with documented approximations):
    - task_id: contract id from contract.json (read from the final round dir);
      falls back to contract_dir.name for cross-phase uniqueness (F1).
    - role, task_class: NOT in the contract schema — always defaulted to
      worker-primary / feature-multi-file with a notes annotation.
    - model: from contract.json worker_model field when present; else defaults
      to _DEFAULT_MODEL. Defaulting noted in 'notes'.
    - review_rounds: count of round-* dirs passed (ALL rounds, not just latest).
    - rejects_real: REJECT verdicts carrying >=1 P0/P1 finding (approximation).
    - rejects_false: REJECT verdicts with only P2 or no findings (approximation).
    - abstained: final round codex-reviewer verdict == ABSTAIN.
    - p0_escaped: F4 — auto-derived True when any review.json carries a P0
      finding (approximation; see _count_outcome_fields docstring).
    - gates_first_try: from outputs/worker/status.json if available; else
      inferred from review_rounds==1. Inference noted in 'notes'.
    - ts: current UTC ISO-8601.
    - reviewers: role names of reviewer output dirs found.
    """
    # F-A: contract.json lives in the round dir, not the contract-K parent.
    contract = _read_contract_json(round_dirs[-1]) if round_dirs else {}
    task_id = str(contract.get("id") or contract_dir.name)

    notes_parts: list[str] = []

    # F-B: role and task_class are NOT in the contract schema — always default.
    role = _DEFAULT_ROLE
    task_class = _DEFAULT_TASK_CLASS
    notes_parts.append(
        f"role defaulted to {_DEFAULT_ROLE}; contract schema carries no role field"
    )
    notes_parts.append(
        f"task_class defaulted to {_DEFAULT_TASK_CLASS}; contract schema carries no task_class field"
    )
    # F-B: the schema field is worker_model, not model.
    model = str(contract.get("worker_model") or _DEFAULT_MODEL)
    if not contract.get("worker_model"):
        notes_parts.append(f"worker_model absent; model defaulted to {_DEFAULT_MODEL}")

    # F3/F4: pass ALL round_dirs; _count_outcome_fields also auto-derives p0_escaped.
    rejects_real, rejects_false, review_rounds, abstained, p0_escaped = (
        _count_outcome_fields(round_dirs)
    )
    gates_first_try_val, was_inferred = _gates_first_try(round_dirs)
    if was_inferred:
        notes_parts.append("gates_first_try inferred from review_rounds")

    # Collect reviewer names from outputs/ dirs of the final round.
    reviewers: list[str] = []
    if round_dirs:
        final_outputs = round_dirs[-1] / "outputs"
        if final_outputs.exists():
            reviewers = [
                d.name for d in sorted(final_outputs.iterdir())
                if d.is_dir() and d.name != "worker"
            ]

    outcome: dict[str, Any] = {
        "gates_first_try": gates_first_try_val,
        "review_rounds": review_rounds,
        "rejects_real": rejects_real,
    }
    if rejects_false:
        outcome["rejects_false"] = rejects_false
    if abstained:
        outcome["abstained"] = abstained
    # F4: include p0_escaped in outcome when auto-derived as True.
    if p0_escaped:
        outcome["p0_escaped"] = True

    record: dict[str, Any] = {
        "ts": _utc_now_iso(),
        "task_id": task_id,
        "role": role,
        "task_class": task_class,
        "model": model,
        "outcome": outcome,
    }
    if reviewers:
        record["reviewers"] = reviewers
    if notes_parts:
        record["notes"] = "; ".join(notes_parts)
    return record


def _round_num(round_dir: Path) -> int:
    # Mirrors _evidence._round_num: numeric key prevents lexical misordering
    # when round count reaches 10+ (round-9 sorts after round-10 lexically).
    try:
        return int(round_dir.name.split("-", 1)[1])
    except (IndexError, ValueError):
        return -1


def _all_round_dirs_for_contract(contract_dir: Path) -> list[Path]:
    # Sorted numerically so round-10, round-11 follow round-9 (not precede it).
    return sorted(contract_dir.glob("round-*"), key=_round_num)


def append_phase_records(
    project_root: Path,
    contracts_root: Path,
) -> int:
    """Discover finished contracts, build records, append to ledger (idempotent).

    Uses _evidence.latest_round_dirs_for_active_phase to enumerate contracts
    under the current iteration's max phase. For each contract, ALL round-*
    dirs are passed to build_record_from_round_dirs (F1/F3 fix — the original
    code only passed [latest_round_dir], dropping earlier rounds' outcome data).

    task_id collision across phases: contract.json's 'id' field is the stable
    unique id. When absent, falls back to contract_dir.name (e.g., "contract-1")
    which is unique within a phase but may collide across phases if the same
    contract slot is reused. In that case, identical task_ids are skipped by the
    existing-ids guard, so the second phase's record is silently dropped. Callers
    should set contract.json 'id' to a UUID to avoid this.

    Args:
        project_root: repo root where .claude/routing/ledger.yaml lives.
        contracts_root: typically STATE_DIR / "contracts" from orchestrator.

    Returns:
        Count of new records appended (0 on idempotent re-run or empty contracts).
    """
    ledger_path = project_root / ".claude" / "routing" / "ledger.yaml"

    # latest_round_dirs returns one round-* per contract; we use it to discover
    # which contracts are active, then fetch ALL their rounds ourselves.
    # Discovery happens outside the lock to minimise lock-hold time, but the
    # actual load→mutate→save is protected by ledger_transaction so two
    # concurrent callers cannot produce a lost-update.
    latest_round_dirs = _evidence.latest_round_dirs_for_active_phase(contracts_root)

    appended = 0
    with ledger_transaction(ledger_path) as txn:
        ledger = txn.ledger
        existing_ids = {r.get("task_id") for r in ledger.get("records") or []}

        for latest_round in latest_round_dirs:
            # contract_dir is the parent of the round-* dir.
            contract_dir = latest_round.parent
            # F-A: contract.json lives in the round dir, not the contract-K parent.
            contract = _read_contract_json(latest_round)
            task_id = str(contract.get("id") or contract_dir.name)
            if task_id in existing_ids:
                print(
                    f"append_phase_records: skipping duplicate task_id {task_id!r} "
                    "(already in ledger; contract.json may lack a stable 'id' — "
                    "set one to avoid cross-phase collisions)",
                    file=sys.stderr,
                )
                continue
            # F1/F3: collect ALL rounds for this contract, not just the latest.
            all_rounds = _all_round_dirs_for_contract(contract_dir)
            record = build_record_from_round_dirs(contract_dir, all_rounds)
            ledger.setdefault("records", []).append(record)
            existing_ids.add(task_id)
            appended += 1

        if appended:
            txn.commit()
    return appended

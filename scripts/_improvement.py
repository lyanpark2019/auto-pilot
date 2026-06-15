"""Improvement-ticket identity + durable ledger I/O for the hermes-loop miner.

Single source of truth for:
  - the per-pattern *fingerprint* (sha256 over source / file basename /
    normalized issue / candidate asset),
  - the per-project ledger home (`~/.claude/projects/<slug>/improvements/`),
  - schema validation against ``schemas/improvement-ticket.schema.json``,
  - the concurrency-safe ``bump_or_create`` read-modify-write of a ticket file.

No LLM, no ``datetime.now()`` in the hot path — the caller injects ``now`` so
the layer stays deterministic and testable. Ledger writes are flock + atomic
temp+rename: the atomic write reuses ``_contract.atomic_write_text``; the
exclusive lock is a per-fingerprint ``<fp>.json.lock`` sidecar held across the
read-modify-write (the plan's prescribed shape — a per-ticket lock, finer than
``_contract.write_lock`` which locks a whole directory).
"""
from __future__ import annotations

import fcntl
import hashlib
import hmac
import json
import os
import re
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import jsonschema

import _contract

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "improvement-ticket.schema.json"

Ticket = dict[str, object]

_UNIT_SEP = "\x1f"
_PHASE_RE = re.compile(r"\bphase-\d+\b")
_PATH_RE = re.compile(r"(?:\.{0,2}/)?(?:[\w.-]+/)+[\w.-]+")
_LINE_RE = re.compile(r":\d+")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}(?:t[\d:]+(?:z|[+-]\d{2}:?\d{2})?)?")

_VALIDATOR: jsonschema.Draft202012Validator | None = None


def _read_plugin_version() -> str:
    here = Path(__file__).resolve()
    for parent in here.parents:
        manifest = parent / ".claude-plugin" / "plugin.json"
        if manifest.exists():
            try:
                data = json.loads(manifest.read_text())
            except (OSError, json.JSONDecodeError):
                return "0"
            version = data.get("version")
            return version if isinstance(version, str) else "0"
    return "0"


PLUGIN_VERSION: str = _read_plugin_version()


def normalize_issue(text: str) -> str:
    """Canonicalize a raw issue string into a stable fingerprint seed.

    Lowercases, strips a leading/embedded ``phase-N`` token, absolute/relative
    paths, ``:NN`` line references, ISO-8601 dates, then collapses whitespace.
    Line / path / date / phase noise is removed so the *same* logical finding at
    a shifted line, different path, or different run-date fingerprints identically.
    """
    lowered = text.lower()
    lowered = _PHASE_RE.sub(" ", lowered)
    lowered = _DATE_RE.sub(" ", lowered)
    lowered = _LINE_RE.sub(" ", lowered)
    lowered = _PATH_RE.sub(" ", lowered)
    return " ".join(lowered.split())


def compute_fingerprint(source: str, file_basename: str, issue: str,
                        candidate_asset: str | None) -> str:
    """sha256 hex of ``source ‖ file_basename ‖ normalize_issue(issue) ‖ asset``.

    The full normalized issue text is kept (no truncation) so semantically
    distinct findings cannot collide.
    """
    seed = _UNIT_SEP.join([
        source,
        file_basename,
        normalize_issue(issue),
        candidate_asset or "",
    ])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


def project_slug(repo_root: Path) -> str:
    """``~/.claude/projects/<slug>`` style slug for a repo root."""
    return str(repo_root.resolve()).replace("/", "-")


def repo_fingerprint(repo_root: Path) -> str:
    """Stable 16-char id of the target repo — git remote URL, else abspath."""
    seed = str(repo_root.resolve())
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            seed = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def ledger_dir(repo_root: Path, commit_to: Path | None) -> Path:
    """Resolve the ledger directory: opt-in ``commit_to`` else the home ledger."""
    if commit_to is not None:
        return commit_to
    return Path.home() / ".claude" / "projects" / project_slug(repo_root) / "improvements"


def _validator() -> jsonschema.Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = json.loads(SCHEMA_PATH.read_text())
        _VALIDATOR = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
    return _VALIDATOR


def validate_ticket(obj: Ticket) -> None:
    """Validate a ticket dict against the schema; raise ``ValidationError``."""
    _validator().validate(obj)


@dataclass(frozen=True)
class Observation:
    """One observed recurrence of a friction pattern, pre-fingerprint."""

    source: str
    file_basename: str
    issue: str
    candidate_asset: str | None
    run_id: str
    snippet: str
    source_path: str = ""


@contextmanager
def ledger_lock(lock_path: Path) -> Iterator[None]:
    """Exclusive flock on ``<fp>.json.lock``, held across the read-modify-write."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    fd = lock_path.open("r+")
    try:
        fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        finally:
            fd.close()


_ledger_lock = ledger_lock  # backward-compat alias


_KEY_SIZE = 32


def _key_path() -> Path:
    """Resolve the attest-key path at call time so HOME overrides take effect."""
    return Path.home() / ".claude" / "auto-pilot" / "attest.key"


def local_key() -> bytes:
    """Return the local HMAC key, creating it (mode 0600) if absent.

    The key directory is created with mode 0700. The key file is written
    atomically with O_CREAT|O_EXCL so concurrent first-call races are safe
    (both callers succeed: one creates, the loser gets EEXIST and reads).
    Returns raw 32 bytes. Never overwrites an existing key.
    """
    path = _key_path()
    if path.exists():
        return path.read_bytes()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    raw = os.urandom(_KEY_SIZE)
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, raw)
        finally:
            os.close(fd)
    except FileExistsError:
        # Another process created the file between our exists() check and open.
        pass
    return path.read_bytes()


def _canonical_identity(ticket: Ticket) -> bytes:
    """Stable UTF-8 bytes covering the fields that define a ticket's identity.

    Bound fields: fingerprint, source, candidate_asset, pattern, evidence
    (run_id + snippet pairs, sorted for order-independence).  ``state`` is
    deliberately excluded — it mutates via _promotion.transition without
    re-stamping; state-transition re-stamping is deferred to the enforcement
    phase.  ``pattern`` never changes post-seed so binding it is safe across
    all promotion-state transitions.

    Sorted by (run_id, snippet) to mirror the dedup key _apply_bump uses so
    that evidence reordering does not invalidate existing attestations.
    """
    raw = ticket.get("evidence", [])
    evidence: list[dict[str, str]] = list(raw) if isinstance(raw, list) else []
    payload = {
        "fingerprint": ticket.get("fingerprint"),
        "source": ticket.get("source"),
        "candidate_asset": ticket.get("candidate_asset"),
        "pattern": ticket.get("pattern", ""),
        "evidence": [
            {"run_id": e.get("run_id", ""), "snippet": e.get("snippet", "")}
            for e in sorted(evidence, key=lambda e: (e.get("run_id", ""), e.get("snippet", "")))
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def stamp_provenance(ticket: Ticket, *, key: bytes, now: datetime) -> Ticket:
    """Attach an HMAC-SHA-256 attestation to a ticket dict (mutates in place).

    ``now`` is injected by the caller so the stamp path remains datetime.now()-free
    and fully testable. The MAC covers the canonical identity bytes derived from
    the ticket's fingerprint, source, candidate_asset, and deduplicated evidence.
    """
    ts = now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mac = hmac.new(key, _canonical_identity(ticket), hashlib.sha256).hexdigest()
    ticket["provenance"] = {
        "algo": "hmac-sha256",
        "attestation": mac,
        "signed_at": ts,
        "identity_version": 1,
    }
    return ticket


def verify_ticket_provenance(
    ticket: Ticket, *, key: bytes, strict: bool = False
) -> tuple[bool, str]:
    """Pure provenance verifier — never calls datetime.now().

    Returns (ok, reason) where reason is one of:
      "legacy-unsigned"       — no provenance field (ok=True unless strict=True)
      "attestation-mismatch"  — HMAC does not match (ok=False)
      "distinct-runs-inflated" — distinct_runs > len(unique run_ids) (ok=False)
      "verified"              — MAC matches and counts are consistent (ok=True)
    """
    prov = ticket.get("provenance")
    if prov is None:
        return (not strict, "legacy-unsigned")

    prov_dict: dict[str, object] = prov if isinstance(prov, dict) else {}
    expected = hmac.new(key, _canonical_identity(ticket), hashlib.sha256).hexdigest()
    actual = str(prov_dict.get("attestation", ""))
    if not hmac.compare_digest(expected, actual):
        return (False, "attestation-mismatch")

    raw = ticket.get("evidence", [])
    evidence: list[dict[str, str]] = list(raw) if isinstance(raw, list) else []
    unique_run_ids = {e.get("run_id", "") for e in evidence}
    distinct = ticket.get("distinct_runs", 0)
    if int(distinct if isinstance(distinct, int) else 0) > len(unique_run_ids):
        return (False, "distinct-runs-inflated")

    return (True, "verified")


def _seed_ticket(fp: str, obs: Observation, repo_fp: str, ts: str) -> Ticket:
    return {
        "schema_version": 1,
        "fingerprint": fp,
        "state": "candidate",
        "pattern": normalize_issue(obs.issue) or obs.source,
        "source": obs.source,
        "candidate_asset": obs.candidate_asset,
        "occurrences": 0,
        "distinct_runs": 0,
        "first_seen": ts,
        "last_seen": ts,
        "plugin_version": PLUGIN_VERSION,
        "repo_fingerprint": repo_fp,
        "evidence": [],
        "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
    }


def _apply_bump(ticket: Ticket, obs: Observation, repo_fp: str, ts: str) -> Ticket:
    raw = ticket.get("evidence", [])
    evidence: list[dict[str, str]] = list(raw) if isinstance(raw, list) else []
    seen = {(e["run_id"], e["snippet"]) for e in evidence}
    key = (obs.run_id, obs.snippet)
    if key not in seen:
        entry: dict[str, str] = {"run_id": obs.run_id, "snippet": obs.snippet}
        if obs.source_path:
            entry["source_path"] = obs.source_path
        evidence.append(entry)
    ticket["evidence"] = evidence
    ticket["occurrences"] = len(evidence)
    ticket["distinct_runs"] = len({e["run_id"] for e in evidence})
    ticket["repo_fingerprint"] = repo_fp
    ticket["last_seen"] = ts
    return ticket


def _load_ticket(path: Path) -> Ticket | None:
    """Load an existing ticket, or None if absent/corrupt/schema-invalid.

    A syntactically valid but schema-invalid payload (``{}``, malformed
    ``evidence`` entries, a hand-edit) returns None so the caller reseeds — the
    "degrade, never crash" contract holds even for structurally corrupt files.
    """
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    try:
        validate_ticket(loaded)
    except jsonschema.ValidationError:
        return None
    return loaded


def bump_or_create(ledger: Path, obs: Observation, *, repo_root: Path,
                   now: datetime, dry_run: bool) -> Ticket:
    """Read-modify-write one ticket under flock + atomic temp+rename.

    Builds the fingerprint, loads (or seeds) ``ledger/<fp>.json``, dedups
    evidence on ``(run_id, snippet)``, recomputes ``occurrences`` /
    ``distinct_runs``, stamps ``last_seen``, validates, and persists. When
    ``dry_run`` the projected ticket is returned without touching disk (no
    directory is created). ``repo_fingerprint`` is derived from ``repo_root``,
    never from the ledger location. A corrupt existing ticket is reseeded.
    """
    fp = compute_fingerprint(obs.source, obs.file_basename, obs.issue, obs.candidate_asset)
    ts = now.isoformat().replace("+00:00", "Z")
    repo_fp = repo_fingerprint(repo_root)
    ticket_path = ledger / f"{fp}.json"

    key = local_key()

    if dry_run:
        ticket = _load_ticket(ticket_path) or _seed_ticket(fp, obs, repo_fp, ts)
        ticket = _apply_bump(ticket, obs, repo_fp, ts)
        stamp_provenance(ticket, key=key, now=now)
        validate_ticket(ticket)
        return ticket

    lock_path = ledger / f"{fp}.json.lock"
    with _ledger_lock(lock_path):
        ticket = _load_ticket(ticket_path) or _seed_ticket(fp, obs, repo_fp, ts)
        ticket = _apply_bump(ticket, obs, repo_fp, ts)
        stamp_provenance(ticket, key=key, now=now)
        validate_ticket(ticket)
        _contract.atomic_write_text(
            ticket_path, json.dumps(ticket, indent=2, sort_keys=True) + "\n"
        )
    return ticket

"""Escalation-record identity + durable ledger I/O (inc2 Phase 3).

Fingerprint, bump_or_create RMW, drive_enrich seam, CLI subparsers.
No datetime.now() / date.today() in library functions — ``now`` is a caller
parameter.  CLI cmd_* handlers may call datetime.now(timezone.utc).
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import jsonschema

import _contract
from _improvement import PLUGIN_VERSION, ledger_lock, project_slug, repo_fingerprint

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "escalation-record.schema.json"
)
_VALIDATOR: jsonschema.Draft202012Validator | None = None
_UNIT_SEP = "\x1f"
_WS_RE = re.compile(r"\s+")
_PROBLEM_CLASS_CHOICES = [
    "enrich-gate-reject", "promotion-gate-unmet", "contract-schema-gap",
    "doom-loop", "unknown-library", "unresolved-error", "other",
]
TRANSITIONS: dict[str, set[str]] = {
    "open": {"enriched", "abandoned"},
    "enriched": {"resolved", "abandoned"},
    "resolved": set(),
    "abandoned": set(),
}


def _can_transition(cur: str, new: str) -> bool:
    """Return True if transitioning from cur to new is legal (or a same-state refresh)."""
    return new == cur or new in TRANSITIONS.get(cur, set())


def _validator() -> jsonschema.Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = json.loads(SCHEMA_PATH.read_text())
        _VALIDATOR = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
    return _VALIDATOR


def validate_escalation(obj: dict[str, Any]) -> None:
    """Validate a record dict against the schema; raise ValidationError."""
    _validator().validate(obj)


def normalize_enrich_query(q: str) -> str:
    """Lowercase + collapse internal whitespace + strip."""
    return _WS_RE.sub(" ", q.lower()).strip()


def compute_fingerprint(problem_class: str, suggested_enrich_query: str) -> str:
    """sha256 hex of ``problem_class ‖ normalize_enrich_query(query)``."""
    seed = _UNIT_SEP.join([problem_class, normalize_enrich_query(suggested_enrich_query)])
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Observation:
    """One observed occurrence of an escalation event, pre-fingerprint."""

    problem_class: str
    suggested_enrich_query: str
    approach: str
    outcome: str
    run_id: str
    snippet: str
    source_path: str = ""
    locator: str = ""


def _seed_record(fp: str, obs: Observation, repo_fp: str, ts: str) -> dict[str, Any]:
    tried_entry: dict[str, Any] = {"approach": obs.approach}
    if obs.outcome:
        tried_entry["outcome"] = obs.outcome
    if obs.locator:
        tried_entry["locator"] = obs.locator
    ev_entry: dict[str, Any] = {"run_id": obs.run_id, "snippet": obs.snippet}
    if obs.source_path:
        ev_entry["source_path"] = obs.source_path
    if obs.locator:
        ev_entry["locator"] = obs.locator
    return {
        "schema_version": 1,
        "fingerprint": fp,
        "state": "open",
        "problem_class": obs.problem_class,
        "tried": [tried_entry],
        "evidence": [ev_entry],
        "suggested_enrich_query": obs.suggested_enrich_query,
        "first_seen": ts,
        "last_seen": ts,
        "occurrences": 1,
        "distinct_runs": 1,
        "plugin_version": PLUGIN_VERSION,
        "repo_fingerprint": repo_fp,
    }


def _apply_bump(
    record: dict[str, Any], obs: Observation, repo_fp: str, ts: str
) -> dict[str, Any]:
    raw_ev: list[Any] = list(record.get("evidence", []))
    seen_ev = {(e["run_id"], e["snippet"]) for e in raw_ev if isinstance(e, dict)}
    if (obs.run_id, obs.snippet) not in seen_ev:
        ev_entry: dict[str, Any] = {"run_id": obs.run_id, "snippet": obs.snippet}
        if obs.source_path:
            ev_entry["source_path"] = obs.source_path
        if obs.locator:
            ev_entry["locator"] = obs.locator
        raw_ev.append(ev_entry)
    record["evidence"] = raw_ev

    raw_tried: list[Any] = list(record.get("tried", []))
    seen_tried = {
        (t.get("approach", ""), t.get("outcome", ""))
        for t in raw_tried if isinstance(t, dict)
    }
    if (obs.approach, obs.outcome) not in seen_tried:
        tried_entry2: dict[str, Any] = {"approach": obs.approach}
        if obs.outcome:
            tried_entry2["outcome"] = obs.outcome
        if obs.locator:
            tried_entry2["locator"] = obs.locator
        raw_tried.append(tried_entry2)
    record["tried"] = raw_tried

    record["occurrences"] = len(raw_ev)
    record["distinct_runs"] = len({e["run_id"] for e in raw_ev if isinstance(e, dict)})
    record["repo_fingerprint"] = repo_fp
    record["last_seen"] = ts
    return record


def _load_record(path: Path) -> dict[str, Any] | None:
    """Load a record, or None on missing/corrupt/schema-invalid."""
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    try:
        validate_escalation(loaded)
    except jsonschema.ValidationError:
        return None
    return loaded


def ledger_dir(repo_root: Path, commit_to: Path | None) -> Path:
    """Resolve the escalation ledger: opt-in commit_to else home-store."""
    if commit_to is not None:
        return commit_to
    return Path.home() / ".claude" / "projects" / project_slug(repo_root) / "escalations"


def bump_or_create(
    ledger: Path,
    obs: Observation,
    *,
    repo_root: Path,
    now: datetime,
    dry_run: bool,
) -> dict[str, Any]:
    """Read-modify-write one record under flock + atomic temp+rename.

    Dedup evidence on (run_id, snippet), dedup tried on (approach, outcome).
    dry_run returns projected record without disk touch.  Corrupt record reseeds.
    """
    if not normalize_enrich_query(obs.suggested_enrich_query):
        raise ValueError("suggested_enrich_query must contain non-whitespace content")
    fp = compute_fingerprint(obs.problem_class, obs.suggested_enrich_query)
    ts = now.isoformat().replace("+00:00", "Z")
    repo_fp = repo_fingerprint(repo_root)
    record_path = ledger / f"{fp}.json"

    if dry_run:
        record = _load_record(record_path) or _seed_record(fp, obs, repo_fp, ts)
        record = _apply_bump(record, obs, repo_fp, ts)
        validate_escalation(record)
        return record

    lock_path = ledger / f"{fp}.json.lock"
    with ledger_lock(lock_path):
        record = _load_record(record_path) or _seed_record(fp, obs, repo_fp, ts)
        record = _apply_bump(record, obs, repo_fp, ts)
        validate_escalation(record)
        _contract.atomic_write_text(
            record_path, json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
    return record


def _record_enrichment(
    record: dict[str, Any],
    query: str,
    counts: dict[str, int],
    *,
    now: datetime,
    retrieved_date: str,
) -> dict[str, Any]:
    """Stamp enrichment sub-doc onto record and set state → 'enriched'."""
    if not _can_transition(record.get("state", ""), "enriched"):
        raise ValueError(
            f"illegal escalation transition {record.get('state')!r}->'enriched'"
        )
    ts = now.isoformat().replace("+00:00", "Z")
    record["enrichment"] = {
        "query": query,
        "enriched_at": ts,
        "retrieved_date": retrieved_date,
        "counts": {
            "admitted": counts.get("admitted", 0),
            "rejected": counts.get("rejected", 0),
            "written": counts.get("written", 0),
            "unchanged": counts.get("unchanged", 0),
        },
    }
    record["state"] = "enriched"
    return record


def record_resolution(
    record: dict[str, Any], new_state: str, *, now: datetime
) -> dict[str, Any]:
    """Transition enriched|open -> resolved|abandoned; FSM-guarded. Caller holds the
    lock + validates + atomic-writes (mirrors _record_enrichment)."""
    if new_state not in ("resolved", "abandoned"):
        raise ValueError(f"invalid resolution state {new_state!r}")
    cur = record.get("state", "")
    if cur in ("resolved", "abandoned"):
        raise ValueError(f"record already terminal: {cur!r}")
    if not _can_transition(cur, new_state):
        raise ValueError(
            f"illegal escalation transition {cur!r}->{new_state!r}"
        )
    record["resolved_at"] = now.isoformat().replace("+00:00", "Z")
    record["state"] = new_state
    return record


def drive_enrich(
    ledger: Path,
    fp: str,
    fetcher: Any,
    vault: Path,
    *,
    retrieved_date: str,
    now: datetime,
    tiers: tuple[str, ...] = ("official", "community"),
    dry_run: bool = False,
) -> dict[str, int]:
    """Fetch-and-persist for the record's enrich query; stamp enrichment block.

    Returns counts from fetch_and_persist.  ``now`` is injected — not generated here.
    """
    from _enrich_fetch import fetch_and_persist  # noqa: PLC0415

    record_path = ledger / f"{fp}.json"
    record = _load_record(record_path)
    if record is None:
        raise FileNotFoundError(f"no escalation record at {record_path}")

    if not _can_transition(record.get("state", ""), "enriched"):
        raise ValueError(
            f"illegal escalation transition {record.get('state')!r}->'enriched'"
        )

    query: str = str(record.get("suggested_enrich_query", ""))
    counts = fetch_and_persist(
        fetcher, query, vault, retrieved_date=retrieved_date, tiers=tiers, dry_run=dry_run
    )

    if dry_run:
        return counts

    lock_path = ledger / f"{fp}.json.lock"
    with ledger_lock(lock_path):
        record = _load_record(record_path)
        if record is None:
            raise FileNotFoundError(f"record disappeared at {record_path}")
        record = _record_enrichment(
            record, query, counts, now=now, retrieved_date=retrieved_date
        )
        validate_escalation(record)
        _contract.atomic_write_text(
            record_path, json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
    return counts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def register_cli_subparsers(sub: Any) -> None:
    """Register escalation-record / escalation-list / escalation-enrich / escalation-resolve."""
    p_er = sub.add_parser("escalation-record")
    p_er.add_argument("--problem-class", required=True, choices=_PROBLEM_CLASS_CHOICES,
                      dest="problem_class")
    p_er.add_argument("--query", required=True, dest="query")
    p_er.add_argument("--approach", required=True)
    p_er.add_argument("--outcome", default="")
    p_er.add_argument("--run-id", required=True, dest="run_id")
    p_er.add_argument("--snippet", required=True)
    p_er.add_argument("--repo-root", default=".", dest="repo_root")
    p_er.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_er.set_defaults(func=cmd_escalation_record)

    p_el = sub.add_parser("escalation-list")
    p_el.add_argument("--repo-root", default=".", dest="repo_root")
    p_el.add_argument("--json", action="store_true")
    p_el.add_argument("--state", default=None)
    p_el.set_defaults(func=cmd_escalation_list)

    p_ee = sub.add_parser("escalation-enrich")
    p_ee.add_argument("prefix")
    p_ee.add_argument("--counts", required=True,
                      help='JSON string e.g. \'{"admitted":1,"rejected":0,"written":1,"unchanged":0}\'')
    p_ee.add_argument("--query", default=None)
    p_ee.add_argument("--retrieved-date", required=True, dest="retrieved_date")
    p_ee.add_argument("--repo-root", default=".", dest="repo_root")
    p_ee.add_argument("--vault", default=None)
    p_ee.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_ee.set_defaults(func=cmd_escalation_enrich)

    p_er2 = sub.add_parser("escalation-resolve")
    p_er2.add_argument("prefix")
    p_er2.add_argument("new_state", choices=["resolved", "abandoned"])
    p_er2.add_argument("--repo-root", default=".", dest="repo_root")
    p_er2.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_er2.set_defaults(func=cmd_escalation_resolve)


def _resolve_fp(ledger: Path, prefix: str) -> str:
    matches = [p.stem for p in ledger.glob(f"{prefix}*.json")]
    if not matches:
        raise KeyError(f"no escalation record matches prefix {prefix!r}")
    if len(matches) > 1:
        raise KeyError(f"ambiguous prefix {prefix!r}: {sorted(matches)}")
    return matches[0]


def cmd_escalation_record(args: Any) -> int:
    """Create or bump an escalation record."""
    import sys  # noqa: PLC0415

    repo_root = Path(getattr(args, "repo_root", "."))
    ledger = ledger_dir(repo_root, None)
    obs = Observation(
        problem_class=args.problem_class,
        suggested_enrich_query=args.query,
        approach=args.approach,
        outcome=getattr(args, "outcome", ""),
        run_id=args.run_id,
        snippet=args.snippet,
    )
    try:
        record = bump_or_create(
            ledger, obs, repo_root=repo_root,
            now=datetime.now(timezone.utc), dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


def cmd_escalation_list(args: Any) -> int:
    """List escalation records as table or JSON lines."""
    repo_root = Path(getattr(args, "repo_root", "."))
    led = ledger_dir(repo_root, None)
    if not led.exists():
        if not getattr(args, "json", False):
            print("(no ledger)")
        return 0

    records: list[dict[str, Any]] = []
    for path in sorted(led.glob("*.json")):
        try:
            obj = json.loads(path.read_text())
            validate_escalation(obj)
            records.append(obj)
        except Exception:  # noqa: BLE001
            continue

    if getattr(args, "state", None):
        records = [r for r in records if r.get("state") == args.state]

    if getattr(args, "json", False):
        for r in records:
            print(json.dumps(r))
        return 0

    if not records:
        print("(no escalations)")
        return 0

    hdr = f"{'FP':10}  {'CLASS':22}  {'RUNS':4}  {'STATE':10}  QUERY"
    print(hdr)
    print("-" * len(hdr))
    for r in records:
        print(
            f"{str(r.get('fingerprint',''))[:8]:10}  "
            f"{str(r.get('problem_class',''))[:22]:22}  "
            f"{str(r.get('distinct_runs','')):4}  "
            f"{str(r.get('state','')):10}  "
            f"{str(r.get('suggested_enrich_query',''))[:40]}"
        )
    return 0


def cmd_escalation_enrich(args: Any) -> int:
    """Stamp an enrichment block onto an escalation record via prefix."""
    import sys  # noqa: PLC0415

    repo_root = Path(getattr(args, "repo_root", "."))
    led = ledger_dir(repo_root, None)
    try:
        fp = _resolve_fp(led, args.prefix)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        counts_raw: dict[str, int] = json.loads(args.counts)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"error: --counts is not valid JSON: {exc}", file=sys.stderr)
        return 1

    record_path = led / f"{fp}.json"
    record = _load_record(record_path)
    if record is None:
        print(f"error: no valid record at {record_path}", file=sys.stderr)
        return 1

    query = getattr(args, "query", None) or str(record.get("suggested_enrich_query", ""))
    now = datetime.now(timezone.utc)

    if args.dry_run:
        try:
            projected = _record_enrichment(
                dict(record), query, counts_raw, now=now, retrieved_date=args.retrieved_date
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            validate_escalation(projected)
        except jsonschema.ValidationError as exc:
            print(f"error: validation failed: {exc.message}", file=sys.stderr)
            return 1
        print(json.dumps(counts_raw))
        return 0

    lock_path = led / f"{fp}.json.lock"
    with ledger_lock(lock_path):
        record = _load_record(record_path)
        if record is None:
            print(f"error: record disappeared at {record_path}", file=sys.stderr)
            return 1
        try:
            record = _record_enrichment(
                record, query, counts_raw, now=now, retrieved_date=args.retrieved_date
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            validate_escalation(record)
        except jsonschema.ValidationError as exc:
            print(f"error: validation failed: {exc.message}", file=sys.stderr)
            return 1
        _contract.atomic_write_text(
            record_path, json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
    print(json.dumps(counts_raw))
    return 0


def cmd_escalation_resolve(args: Any) -> int:
    """Transition an escalation record to resolved|abandoned via prefix."""
    import sys  # noqa: PLC0415

    repo_root = Path(getattr(args, "repo_root", "."))
    led = ledger_dir(repo_root, None)
    try:
        fp = _resolve_fp(led, args.prefix)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    record_path = led / f"{fp}.json"
    now = datetime.now(timezone.utc)

    if args.dry_run:
        record = _load_record(record_path)
        if record is None:
            print(f"error: no valid record at {record_path}", file=sys.stderr)
            return 2
        try:
            projected = record_resolution(dict(record), args.new_state, now=now)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        try:
            validate_escalation(projected)
        except jsonschema.ValidationError as exc:
            print(f"error: validation failed: {exc.message}", file=sys.stderr)
            return 2
        print(json.dumps(projected, indent=2, sort_keys=True))
        return 0

    lock_path = led / f"{fp}.json.lock"
    with ledger_lock(lock_path):
        record = _load_record(record_path)
        if record is None:
            print(f"error: no valid record at {record_path}", file=sys.stderr)
            return 2
        try:
            record = record_resolution(record, args.new_state, now=now)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        try:
            validate_escalation(record)
        except jsonschema.ValidationError as exc:
            print(f"error: validation failed: {exc.message}", file=sys.stderr)
            return 2
        _contract.atomic_write_text(
            record_path, json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0

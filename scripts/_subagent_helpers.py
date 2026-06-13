"""Helpers invoked by subagents (worker, reviewers) at boot + during execution.

These run *inside* the subagent's Claude Code session; PM does NOT call them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Sequence, cast

import jsonschema

import _contract
import _dispatch


class TicketShaMismatchError(Exception):
    """Raised when ticket.ticket_sha does not match recomputed canonical sha."""


def read_ticket(ticket_path: Path) -> dict[str, Any]:
    """Read ticket JSON, validate against schema, verify ticket_sha integrity."""
    data = json.loads(ticket_path.read_text())
    recomputed = _dispatch._compute_ticket_sha({k: v for k, v in data.items() if k != "ticket_sha"})
    if data.get("ticket_sha") != recomputed:
        raise TicketShaMismatchError(
            f"ticket_sha mismatch: {data.get('ticket_sha')!r} != {recomputed!r}"
        )
    _dispatch._validator().validate(data)
    return cast(dict[str, Any], data)


def assert_not_canceled(contract_dir: Path) -> None:
    """Exit 99 if PM has touched <contract_dir>/CANCELED. Cheap to poll."""
    if (contract_dir / "CANCELED").exists():
        sys.exit(99)


def compute_finding_hash(file: str, line: int | None, issue: str) -> str:
    """Standardized finding hash: sha256(file:line:canonical_issue).

    canonical_issue = first 8 lowercased whitespace-separated tokens.
    Same logical finding from any reviewer → same hash → pivot-detector
    counts correctly.
    """
    canonical = " ".join(issue.lower().strip().split()[:8])
    payload = f"{file}:{line if line is not None else '?'}:{canonical}"
    return hashlib.sha256(payload.encode()).hexdigest()


def atomic_write_output(role_output_dir: Path, name: str, data: dict[str, Any]) -> Path:
    """Atomic JSON write to <role_output_dir>/<name>. Same fsync protocol as ContractIO."""
    role_output_dir.mkdir(parents=True, exist_ok=True)
    target = role_output_dir / name
    return _contract.atomic_write_text(target, json.dumps(data, indent=2, sort_keys=True) + "\n")


def write_exit_code(role_output_dir: Path, code: int) -> Path:
    """Write <role_output_dir>/exit-code.txt atomically.

    MUST be called BEFORE mark_done(). Ordering invariant:
      status/review JSON → exit-code.txt → done.marker
    PM reading done.marker is guaranteed to see exit-code.txt + payload.
    """
    role_output_dir.mkdir(parents=True, exist_ok=True)
    return _contract.atomic_write_text(role_output_dir / "exit-code.txt", f"{int(code)}\n")


def mark_done(role_output_dir: Path) -> Path:
    """Touch done.marker. MUST be called LAST after all output + exit-code writes."""
    role_output_dir.mkdir(parents=True, exist_ok=True)
    marker = role_output_dir / "done.marker"
    marker.touch()
    return marker


def main(argv: Sequence[str] | None = None) -> int:
    """Reviewer/worker boot entry point: validate a ticket from the shell.

    `--read-ticket <path>` runs read_ticket (schema + ticket_sha). Exit 2 on a
    ticket_sha mismatch, 3 on schema-invalid, 4 on missing/unreadable JSON, 0 on
    a valid ticket. The reviewer agents shell out here instead of running an
    inert `import` that always exited 0.
    """
    parser = argparse.ArgumentParser(prog="_subagent_helpers")
    parser.add_argument("--read-ticket", metavar="PATH",
                        help="validate ticket schema + ticket_sha, non-zero on failure")
    args = parser.parse_args(argv)

    if args.read_ticket is not None:
        try:
            read_ticket(Path(args.read_ticket))
        except TicketShaMismatchError as exc:
            sys.stderr.write(f"_subagent_helpers: {exc}\n")
            return 2
        except jsonschema.ValidationError as exc:
            sys.stderr.write(f"_subagent_helpers: ticket schema invalid: {exc.message}\n")
            return 3
        except (OSError, json.JSONDecodeError) as exc:
            sys.stderr.write(f"_subagent_helpers: cannot read ticket: {exc}\n")
            return 4
        return 0

    parser.error("no action requested (expected --read-ticket)")


if __name__ == "__main__":
    raise SystemExit(main())

"""Deterministic enrichment gate — inc2-enrich Phase 1.

Evaluates a candidate external-fact dict against the enrichment-evidence schema
and a set of deterministic rules:

  - evidence-complete: snippet non-empty, source_url present, retrieved_date
    valid ISO, sha256 == sha256(snippet.utf-8).
  - official tier: ADMIT iff evidence-complete.
  - community tier: ADMIT iff evidence-complete AND (>=2 corroborations from
    hosts distinct from each other and from the primary host, each sha-valid)
    OR repro_passed is True.
  - llm_judge: recorded in output but NEVER changes the verdict (advisory only;
    "enforce with code, not prompts").

No network calls. Pure, fully testable.

CLI: python3 scripts/_enrich_gate.py <candidate.json>
  Exit 0 = admit, exit 1 = reject.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unicodedata
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent / "schemas" / "enrichment-evidence.schema.json"
)

_VALIDATOR: jsonschema.Draft202012Validator | None = None


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def canonical_sha(snippet: str) -> str:
    """sha256 hex of snippet encoded as UTF-8."""
    return hashlib.sha256(snippet.encode("utf-8")).hexdigest()


def _valid_iso_date(s: str) -> bool:
    """Return True for a valid ISO date (YYYY-MM-DD) or date-time string."""
    if not isinstance(s, str) or not s:
        return False
    # Normalise trailing 'Z' so fromisoformat accepts it on Python ≤3.10.
    normalised = s.strip()
    if normalised.endswith("Z"):
        normalised = normalised[:-1] + "+00:00"
    # Try date-time first (more specific), then plain date.
    try:
        datetime.fromisoformat(normalised)
        return True
    except ValueError:
        pass
    try:
        date.fromisoformat(normalised)
        return True
    except ValueError:
        return False


def _has_visible_content(s: str) -> bool:
    """True iff *s* contains at least one character that is not whitespace
    and not a Unicode format/control/separator char (incl. U+200B zero-width space)."""
    if not isinstance(s, str):
        return False
    for ch in s:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        # Cf=format (includes U+200B), Cc=control, Zs/Zl/Zp=separators
        if cat in ("Cf", "Cc", "Zs", "Zl", "Zp"):
            continue
        return True
    return False


def _canonical_host(url: str) -> str:
    """Lowercased hostname with a single trailing dot stripped; '' when hostless."""
    try:
        h = urllib.parse.urlparse(url).hostname or ""
    except Exception:  # pragma: no cover — urlparse rarely raises
        return ""
    h = h.lower()
    if h.endswith("."):
        h = h[:-1]
    return h


# ---------------------------------------------------------------------------
# Schema validator (lazy singleton)
# ---------------------------------------------------------------------------


def _validator() -> jsonschema.Draft202012Validator:
    global _VALIDATOR
    if _VALIDATOR is None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        _VALIDATOR = jsonschema.Draft202012Validator(
            schema, format_checker=jsonschema.FormatChecker()
        )
    return _VALIDATOR


# ---------------------------------------------------------------------------
# Core gate
# ---------------------------------------------------------------------------


def evaluate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a candidate enrichment-evidence dict.

    Returns::

        {
            "verdict": "admit" | "reject",
            "reasons": [str, ...],
            "evidence_complete": bool,
            "source_tier": str,
            "advisory_judge": <llm_judge dict or None>,
        }

    Never raises — all exceptions are caught and turned into reject reasons.
    """
    reasons: list[str] = []
    advisory_judge: dict[str, Any] | None = None

    # ------------------------------------------------------------------ 0. Type guard
    if not isinstance(candidate, dict):
        return {
            "verdict": "reject",
            "reasons": ["candidate is not an object"],
            "evidence_complete": False,
            "source_tier": "",
            "advisory_judge": None,
        }

    # ------------------------------------------------------------------ 1. Schema
    try:
        _validator().validate(candidate)
    except jsonschema.ValidationError as exc:
        return {
            "verdict": "reject",
            "reasons": [f"schema-invalid: {exc.message}"],
            "evidence_complete": False,
            "source_tier": candidate.get("source_tier", ""),
            "advisory_judge": None,
        }
    except Exception as exc:  # pragma: no cover
        return {
            "verdict": "reject",
            "reasons": [f"schema-invalid: unexpected error {exc}"],
            "evidence_complete": False,
            "source_tier": candidate.get("source_tier", ""),
            "advisory_judge": None,
        }

    source_tier: str = candidate["source_tier"]
    snippet: str = candidate["snippet"]
    source_url: str = candidate["source_url"]
    retrieved_date: str = candidate["retrieved_date"]
    sha256_claim: str = candidate["sha256"]

    # ------------------------------------------------------------------ 2. Evidence completeness
    evidence_complete = True

    if not _has_visible_content(snippet):
        reasons.append("snippet has no visible content")
        evidence_complete = False

    if not source_url:
        reasons.append("source_url is empty")
        evidence_complete = False

    if not _valid_iso_date(retrieved_date):
        reasons.append("retrieved_date not ISO")
        evidence_complete = False

    if snippet and sha256_claim != canonical_sha(snippet):
        reasons.append("sha256 mismatch (tamper)")
        evidence_complete = False

    # ------------------------------------------------------------------ 3. Reject if incomplete
    if not evidence_complete:
        advisory_judge = candidate.get("llm_judge")
        _record_advisory_note(advisory_judge, "reject", reasons)
        return {
            "verdict": "reject",
            "reasons": reasons,
            "evidence_complete": False,
            "source_tier": source_tier,
            "advisory_judge": advisory_judge,
        }

    # ------------------------------------------------------------------ 4. Official tier
    if source_tier == "official":
        advisory_judge = candidate.get("llm_judge")
        _record_advisory_note(advisory_judge, "admit", reasons)
        return {
            "verdict": "admit",
            "reasons": reasons,
            "evidence_complete": True,
            "source_tier": source_tier,
            "advisory_judge": advisory_judge,
        }

    # ------------------------------------------------------------------ 5. Community tier
    repro_passed: bool | None = candidate.get("repro_passed")
    corroborations: list[dict[str, Any]] = candidate.get("corroborations") or []

    if repro_passed is True:
        advisory_judge = candidate.get("llm_judge")
        _record_advisory_note(advisory_judge, "admit", reasons)
        return {
            "verdict": "admit",
            "reasons": reasons,
            "evidence_complete": True,
            "source_tier": source_tier,
            "advisory_judge": advisory_judge,
        }

    # Count sha-valid corroborations with hosts distinct from each other and
    # from the primary source_url host.  All four conditions must hold:
    #   1. sha256 matches (tamper guard)
    #   2. snippet has visible content (not blank/zero-width/control chars)
    #   3. corroboration URL has a non-empty canonical host (hostless URNs etc. never count)
    #   4. canonical host not already seen (dedup against primary + prior corroborations)
    primary_host = _canonical_host(source_url)
    seen_hosts: set[str] = {primary_host} if primary_host else set()
    valid_distinct_count = 0
    bad_sha_count = 0

    for corr in corroborations:
        corr_snippet = corr.get("snippet", "")
        corr_sha = corr.get("sha256", "")
        corr_url = corr.get("source_url", "")
        if canonical_sha(corr_snippet) != corr_sha:
            bad_sha_count += 1
            reasons.append(
                f"corroboration sha256 mismatch (tamper) for url={corr_url!r}"
            )
            continue
        if not _has_visible_content(corr_snippet):
            reasons.append(
                f"corroboration snippet has no visible content for url={corr_url!r}"
            )
            continue
        corr_host = _canonical_host(corr_url)
        if not corr_host:
            reasons.append(
                f"corroboration URL has no host (not an independent source): {corr_url!r}"
            )
            continue
        if corr_host in seen_hosts:
            # Same host as primary or a previous corroboration — not independent.
            reasons.append(
                f"corroboration host not independent: {corr_host!r}"
            )
            continue
        seen_hosts.add(corr_host)
        valid_distinct_count += 1

    if valid_distinct_count >= 2:
        advisory_judge = candidate.get("llm_judge")
        _record_advisory_note(advisory_judge, "admit", reasons)
        return {
            "verdict": "admit",
            "reasons": reasons,
            "evidence_complete": True,
            "source_tier": source_tier,
            "advisory_judge": advisory_judge,
        }

    advisory_judge = candidate.get("llm_judge")
    reasons.append(
        "community tier: needs >=2 independent corroborations or a passing repro"
    )
    _record_advisory_note(advisory_judge, "reject", reasons)
    return {
        "verdict": "reject",
        "reasons": reasons,
        "evidence_complete": True,
        "source_tier": source_tier,
        "advisory_judge": advisory_judge,
    }


def _record_advisory_note(
    llm_judge: dict[str, Any] | None,
    actual_verdict: str,
    reasons: list[str],
) -> None:
    """Append a note when the advisory judge disagrees with the deterministic verdict."""
    if llm_judge is None:
        return
    judge_verdict = llm_judge.get("verdict", "")
    if judge_verdict != actual_verdict:
        reasons.append("llm_judge advisory only — not gating")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        sys.stderr.write("usage: _enrich_gate.py <candidate.json>\n")
        return 2
    path = Path(args[0])
    try:
        candidate = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error reading {path}: {exc}\n")
        return 2

    result = evaluate(candidate)
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0 if result["verdict"] == "admit" else 1


if __name__ == "__main__":
    sys.exit(main())

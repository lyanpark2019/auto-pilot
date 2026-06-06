#!/usr/bin/env python3
"""risk_assess.py — risk-tiered review-gate classifier for changed file paths.

Adapted from oh-my-claudecode scripts/risk-assess.mjs, MIT. Python port of the
OMC risk-assess + review-gate tier concepts, with one auto-pilot extension:
``--extra-risk`` lets the PM inject out-of-band risk for changes that never
appear in a code diff (e.g. Supabase MCP-applied SQL migrations).

Input (union of all provided sources):
  - positional PATH arguments
  - ``--diff-range A..B`` → runs ``git diff --name-only A..B`` (timeout 30s)
  - stdin lines (when no positional paths given and stdin is not a TTY)

Tier classification per path (highest match wins; sub-token exact match with
plural folding, e.g. ``schemas`` → ``schema``):
  critical  auth|oauth|token|session|secret|crypto|payment|billing|webhook
  high      migration|schema|hook|gate|guard|dispatch|contract|security
  medium    source files (.py/.sh/.ts/.js)
  low       config files (.json/.yaml/.yml/.toml) — schemas/ is HIGH, not LOW
  none      docs (.md), dashboard/, .planning/, anything unrecognized
Test-only paths (tests/ dirs, test_* / *_test / *.spec.* files) count one tier
below their subject — a diff that is ONLY plain tests/ comes out LOW.

Output: single-line JSON on stdout —
  {"tier": .., "files": N, "by_tier": {..}, "review_policy": .., "extra_risk": ..}

Exit codes: 0 always (advisory, not a blocker); 2 when ``--fail-on LEVEL`` is
given and the assessed tier ≥ LEVEL (CI use); 1 on operational errors
(git failure); argparse uses 2 for usage errors.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass

TIERS: tuple[str, ...] = ("none", "low", "medium", "high", "critical")
_TIER_RANK: dict[str, int] = {name: rank for rank, name in enumerate(TIERS)}

CRITICAL_TOKENS: frozenset[str] = frozenset(
    {"auth", "oauth", "token", "session", "secret", "crypto",
     "payment", "billing", "webhook"}
)
HIGH_TOKENS: frozenset[str] = frozenset(
    {"migration", "schema", "hook", "gate", "guard", "dispatch",
     "contract", "security"}
)
SOURCE_EXTS: frozenset[str] = frozenset({"py", "sh", "ts", "js"})
CONFIG_EXTS: frozenset[str] = frozenset({"json", "yaml", "yml", "toml"})
DOC_EXTS: frozenset[str] = frozenset({"md"})
NONE_DIR_SEGMENTS: frozenset[str] = frozenset({"dashboard", ".planning"})
TEST_DIR_SEGMENTS: frozenset[str] = frozenset({"test", "tests", "__tests__"})

REVIEW_POLICY: dict[str, str] = {
    "none": "skip-review",
    "low": "single-reviewer",
    "medium": "dual-review",
    "high": "dual-review+gatekeeper(security mode)+tight-rescope",
    "critical": "dual-review+gatekeeper(security mode)+tight-rescope",
}

_GIT_TIMEOUT_SEC = 30.0
_SUB_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class Assessment:
    """Result of classifying a set of changed paths."""

    tier: str
    files: int
    by_tier: dict[str, int]
    review_policy: str
    extra_risk: str | None

    def to_json(self) -> str:
        """Serialize to the single-line JSON contract printed on stdout."""
        return json.dumps(
            {
                "tier": self.tier,
                "files": self.files,
                "by_tier": self.by_tier,
                "review_policy": self.review_policy,
                "extra_risk": self.extra_risk,
            },
            sort_keys=False,
        )


def _sub_tokens(path: str) -> frozenset[str]:
    """Lower-cased alphanumeric sub-tokens of every path segment."""
    return frozenset(_SUB_TOKEN_RE.findall(path.lower()))


def _keyword_hit(tokens: frozenset[str], keywords: frozenset[str]) -> bool:
    """Exact sub-token match with naive plural folding (``hooks`` → ``hook``).

    Deliberately conservative — no substring matching, so ``tokenizer`` does
    NOT trip ``token``. Misses are the PM's job via ``--extra-risk``.
    """
    for tok in tokens:
        if tok in keywords:
            return True
        if tok.endswith("s") and tok[:-1] in keywords:
            return True
    return False


def _extension(path: str) -> str:
    base = path.rsplit("/", 1)[-1].lower()
    if "." not in base[1:]:
        return ""
    return base.rsplit(".", 1)[-1]


def _is_test_path(path: str) -> bool:
    segments = [seg.lower() for seg in path.split("/") if seg]
    if any(seg in TEST_DIR_SEGMENTS for seg in segments[:-1]):
        return True
    base = segments[-1] if segments else ""
    stem = base.rsplit(".", 1)[0] if "." in base else base
    return (
        base.startswith(("test_", "test-"))
        or stem.endswith(("_test", "-test", ".test", ".spec"))
    )


def _classify_subject(path: str) -> str:
    """Tier of a path ignoring any test-path downgrade."""
    tokens = _sub_tokens(path)
    if _keyword_hit(tokens, CRITICAL_TOKENS):
        return "critical"
    if _keyword_hit(tokens, HIGH_TOKENS):
        return "high"
    segments = [seg.lower() for seg in path.split("/") if seg]
    ext = _extension(path)
    if ext in DOC_EXTS or any(seg in NONE_DIR_SEGMENTS for seg in segments[:-1]):
        return "none"
    if ext in SOURCE_EXTS:
        return "medium"
    if ext in CONFIG_EXTS:
        # schemas/*.json never reaches here — the "schema" token is HIGH.
        return "low"
    return "none"


def _downgrade(tier: str) -> str:
    return TIERS[max(_TIER_RANK[tier] - 1, 0)]


def classify_path(path: str) -> str:
    """Return the tier name ("none".."critical") for one changed path."""
    cleaned = path.strip().strip("/")
    if not cleaned:
        return "none"
    subject = _classify_subject(cleaned)
    if _is_test_path(cleaned):
        return _downgrade(subject)
    return subject


def assess(paths: Sequence[str], extra_risk: str | None = None) -> Assessment:
    """Classify ``paths`` and fold in optional out-of-band ``extra_risk``.

    Highest tier wins. Empty input (and no extra risk) → tier "none".
    """
    by_tier: dict[str, int] = {tier: 0 for tier in TIERS}
    for path in paths:
        by_tier[classify_path(path)] += 1
    rank = max(
        (_TIER_RANK[tier] for tier, count in by_tier.items() if count > 0),
        default=0,
    )
    if extra_risk is not None:
        rank = max(rank, _TIER_RANK[extra_risk])
    tier = TIERS[rank]
    return Assessment(
        tier=tier,
        files=len(paths),
        by_tier=by_tier,
        review_policy=REVIEW_POLICY[tier],
        extra_risk=extra_risk,
    )


def changed_files_from_git(
    diff_range: str, timeout: float = _GIT_TIMEOUT_SEC
) -> list[str]:
    """``git diff --name-only <diff_range>`` in the current working directory."""
    proc = subprocess.run(
        ["git", "diff", "--name-only", diff_range],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"git diff --name-only {diff_range!r} failed "
            f"(rc={proc.returncode}): {proc.stderr.strip()}"
        )
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="risk_assess",
        description="Risk-tiered review-gate classifier (advisory; exit 0).",
    )
    parser.add_argument("paths", nargs="*", metavar="PATH",
                        help="changed file paths (else stdin lines)")
    parser.add_argument("--diff-range", metavar="A..B",
                        help="run `git diff --name-only A..B` for the path list")
    parser.add_argument("--extra-risk", choices=TIERS, default=None,
                        help="PM-injected out-of-band risk floor "
                             "(e.g. MCP-applied SQL migration)")
    parser.add_argument("--fail-on", choices=TIERS[1:], default=None,
                        help="exit 2 if assessed tier >= this level (CI use)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths: list[str] = list(args.paths)
    if args.diff_range is not None:
        try:
            paths.extend(changed_files_from_git(args.diff_range))
        except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError) as exc:
            print(f"risk_assess: {exc}", file=sys.stderr)
            return 1
    elif not paths and not sys.stdin.isatty():
        paths = [line.strip() for line in sys.stdin if line.strip()]

    result = assess(paths, extra_risk=args.extra_risk)
    print(result.to_json())

    if args.fail_on is not None and _TIER_RANK[result.tier] >= _TIER_RANK[args.fail_on]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Learning-loop ON/OFF A/B driver with a MOCKED Archon-run seam (Task 10).

This module orchestrates the measurement-integrity machinery around the Archon
workflow WITHOUT performing any live Archon run or model call.  The single live
boundary — ``run_workflow(arm, seed)`` — shells out to ``bun run cli workflow
run`` in production; in tests a fixture replaces it with canned ``review.json``
files.  Everything else here is deterministic and unit-testable.

Pipeline (spec ``docs/specs/2026-06-20-learning-loop-archon-port.md`` Task 10):

  1. Seed a FROZEN stage-A ledger ONCE (real adapter+miner path, ``--run-id``)
     so a recurring class reaches ``distinct_runs>=2`` and is gate-passed.
  2. For every scored arm/pair, run scoring against a per-arm COPY of the frozen
     ledger with mining DISABLED (``SCORING=1``).  Assert the scoring-ledger
     SHA-256 is UNCHANGED across all scored cases (codex P0-3 train/test split).
  3. OFF arm = ``AUTO_PILOT_DISABLE_LEARNINGS=1`` inlined INLINE on the inject
     ``resolve-learnings`` command ONLY — never the subprocess-wide env (codex
     confirm P1; a subprocess-wide var leaks into the Claude provider).
  4. Score each run's ``review.json`` via the deterministic class+location
     ``oracle`` and SHA-256-log it.
  5. PILOT gate: keep only OFF catch-rate in [0.30,0.70]; require >=1 class with
     a real OFF-miss -> ON-catch on >=2 discordant pairs before any powered run;
     else INCONCLUSIVE / KILL.
  6. Stats: Fisher exact one-sided + McNemar (exact) + paired catch-rate delta
     with 95% CI.  PROCEED bar = +0.20.
  7. ON-arm-blind guard: ``resolve-learnings`` must have selected >=1 ticket in
     the ON arm before scoring.

``run_workflow`` is the ONLY function callers mock; the live ``bun`` wiring is
exercised in a later step, not here.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import ab_ledger
import ab_stats
import oracle

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"

PROCEED_DELTA = 0.20
SATURATION_BAND = (0.30, 0.70)
MIN_DISCORDANT_PAIRS = 2

# ---------------------------------------------------------------------------
# Mocked Archon-run seam.  ``run_workflow`` is replaced wholesale in tests.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Seed:
    """One frozen stage-B test diff plus its hidden golden defect."""

    name: str
    diff_path: Path
    golden_class: str
    golden_file: str
    scope: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowResult:
    """What an Archon run hands back: the review.json the reviewer emitted."""

    review_path: Path
    learnings_path: Path | None  # context-bundle/learnings.md (None if not produced)


RunWorkflow = Callable[[str, Seed, Path], WorkflowResult]


def inject_command(
    arm: str,
    *,
    repo_root: Path,
    ledger_dir: Path,
    dest_dir: Path,
    scope: list[str],
    python_bin: str = sys.executable,
) -> str:
    """Build the inject node's ``resolve-learnings`` command string.

    OFF arm inlines ``AUTO_PILOT_DISABLE_LEARNINGS=1`` as a command-string
    prefix so the toggle reaches ONLY ``resolve_learnings`` and never the
    Archon subprocess env (codex confirm P1).  ON arm = same command, no prefix.
    The two arms therefore differ in EXACTLY one bit.
    """
    scope_args = " ".join(f"--scope {s}" for s in scope)
    base = (
        f"{python_bin} {_SCRIPTS / 'orchestrator.py'} resolve-learnings "
        f"--repo-root {repo_root} --ledger-dir {ledger_dir} "
        f"--dest-dir {dest_dir} {scope_args} --sanitized"
    ).strip()
    if arm == "OFF":
        return f"AUTO_PILOT_DISABLE_LEARNINGS=1 {base}"
    if arm == "ON":
        return base
    raise ValueError(f"unknown arm: {arm!r}")


def run_workflow(arm: str, seed: Seed, work_dir: Path) -> WorkflowResult:  # pragma: no cover
    """LIVE seam: ``bun run cli workflow run`` (mocked in every unit test).

    Intentionally a thin shell-out stub.  This module's tests inject a fake in
    its place; the real Archon invocation is wired and exercised in a later
    step, never here, so this body is excluded from coverage.
    """
    raise NotImplementedError(
        "run_workflow is the live Archon seam — inject a mock in tests / wire "
        "`bun run cli workflow run` in the live pilot step."
    )


# Frozen-ledger lifecycle (seed / sha / per-arm copy) lives in ab_ledger to keep
# this module within the size budget.  Re-exported so callers import one symbol set.
seed_frozen_ledger = ab_ledger.seed_frozen_ledger
ledger_sha = ab_ledger.ledger_sha
copy_ledger = ab_ledger.copy_ledger


# ---------------------------------------------------------------------------
# ON-arm-blind guard.
# ---------------------------------------------------------------------------


def assert_on_arm_selected(ledger_dir: Path, scope: list[str]) -> int:
    """Assert ``resolve-learnings`` selects >=1 gate-passed ticket for the ON arm.

    Uses the real ``_learnings.select_tickets`` against the (copied) per-arm
    ledger — exactly the selection the live ON inject node performs.  A zero
    result means the ON arm would run learnings-blind, so the A/B would silently
    measure nothing; we fail LOUD (spec ON-blind guard).
    """
    sys.path.insert(0, str(_SCRIPTS))
    import _learnings  # noqa: PLC0415
    tickets = _learnings.select_tickets(ledger_dir, scope)
    if len(tickets) < 1:
        raise AssertionError(
            f"ON-arm blind: no ticket selected for scope {scope} in {ledger_dir}"
        )
    return len(tickets)


# ---------------------------------------------------------------------------
# Scoring a single run (oracle + SHA log) with the frozen-ledger assertion.
# ---------------------------------------------------------------------------


@dataclass
class ScoredRun:
    arm: str
    seed: str
    caught: bool
    noise: int
    review_sha: str
    ledger_sha: str


def score_arm(
    arm: str,
    seed: Seed,
    *,
    frozen_ledger: Path,
    work_root: Path,
    run_workflow_fn: RunWorkflow,
    expected_ledger_sha: str,
) -> ScoredRun:
    """Run + score ONE arm against a per-arm ledger copy with mining DISABLED.

    Copies the frozen ledger, (for ON) asserts a ticket is selected, runs the
    mocked workflow, scores the review.json by class+location, and asserts the
    scoring ledger SHA is UNCHANGED (no contamination — mine is off, codex P0-3).
    """
    arm_dir = work_root / f"{arm}-{seed.name}"
    arm_dir.mkdir(parents=True, exist_ok=True)
    arm_ledger = copy_ledger(frozen_ledger, arm_dir / "ledger")

    if arm == "ON":
        assert_on_arm_selected(arm_ledger, seed.scope)

    result = run_workflow_fn(arm, seed, arm_dir)
    review = oracle.load_review(result.review_path)
    is_caught = oracle.caught(review, seed.golden_class, seed.golden_file)
    noise = oracle.noise_count(review)
    review_sha = oracle.sha256_file(result.review_path)

    post_sha = ledger_sha(arm_ledger)
    if post_sha != expected_ledger_sha:
        raise AssertionError(
            f"scoring ledger mutated for {arm}/{seed.name}: "
            f"{post_sha} != {expected_ledger_sha} (mine must be DISABLED)"
        )
    return ScoredRun(
        arm=arm, seed=seed.name, caught=is_caught, noise=noise,
        review_sha=review_sha, ledger_sha=post_sha,
    )


# ---------------------------------------------------------------------------
# PILOT (kill gate): anti-saturation band + OFF-miss -> ON-catch discordance.
# ---------------------------------------------------------------------------


@dataclass
class PilotResult:
    verdict: str  # "PROCEED" | "INCONCLUSIVE" | "KILL"
    reason: str
    admitted: list[str]
    off_catch_rates: dict[str, float]
    discordant_classes: dict[str, int]


def run_pilot(
    seeds: list[Seed],
    *,
    frozen_ledger: Path,
    work_root: Path,
    run_workflow_fn: RunWorkflow,
    repeats: int = 1,
) -> PilotResult:
    """OFF-only headroom pilot → admit mid-band diffs, gate on real discordance.

    For each seed: estimate OFF catch-rate (over ``repeats`` runs) and an ON
    catch outcome.  Admit a seed ONLY when its OFF catch-rate is inside
    [0.30,0.70] (anti-saturation).  Require >=1 golden class showing a real
    OFF-miss -> ON-catch on >=MIN_DISCORDANT_PAIRS admitted pairs before any
    powered run; otherwise emit INCONCLUSIVE / KILL (an accepted informative
    outcome → strategic fallback, NOT a crash).
    """
    frozen_sha = ledger_sha(frozen_ledger)
    off_rates: dict[str, float] = {}
    admitted: list[str] = []
    discordant_by_class: dict[str, int] = defaultdict(int)

    for seed in seeds:
        off_hits = 0
        for _ in range(repeats):
            off = score_arm(
                "OFF", seed, frozen_ledger=frozen_ledger, work_root=work_root,
                run_workflow_fn=run_workflow_fn, expected_ledger_sha=frozen_sha,
            )
            off_hits += int(off.caught)
        off_rate = off_hits / repeats
        off_rates[seed.name] = off_rate
        lo, hi = SATURATION_BAND
        if not (lo <= off_rate <= hi):
            continue
        admitted.append(seed.name)
        # Probe the ON outcome on this admitted seed for OFF-miss -> ON-catch.
        on = score_arm(
            "ON", seed, frozen_ledger=frozen_ledger, work_root=work_root,
            run_workflow_fn=run_workflow_fn, expected_ledger_sha=frozen_sha,
        )
        if on.caught and off_rate < 1.0:
            discordant_by_class[seed.golden_class] += 1

    if not admitted:
        return PilotResult(
            "INCONCLUSIVE", "no diff in anti-saturation band [0.30,0.70]",
            admitted, off_rates, dict(discordant_by_class),
        )
    best = max(discordant_by_class.values(), default=0)
    if best < MIN_DISCORDANT_PAIRS:
        return PilotResult(
            "INCONCLUSIVE",
            f"no class with >= {MIN_DISCORDANT_PAIRS} OFF-miss->ON-catch pairs "
            f"(best={best})",
            admitted, off_rates, dict(discordant_by_class),
        )
    return PilotResult(
        "PROCEED", "headroom + real discordance present",
        admitted, off_rates, dict(discordant_by_class),
    )


# ---------------------------------------------------------------------------
# Powered A/B + verdict.
# ---------------------------------------------------------------------------


@dataclass
class ABVerdict:
    verdict: str  # "PROCEED" | "KILL" | "KEEP-DEFERRED"
    catch_rate_on: float
    catch_rate_off: float
    delta: float
    ci_low: float
    ci_high: float
    fisher_p: float
    mcnemar_p: float
    noise_delta: float
    scored: list[dict[str, Any]]
    ledger_sha: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "verdict": self.verdict,
                "catch_rate_on": self.catch_rate_on,
                "catch_rate_off": self.catch_rate_off,
                "delta": self.delta,
                "ci_low": self.ci_low,
                "ci_high": self.ci_high,
                "fisher_p": self.fisher_p,
                "mcnemar_p": self.mcnemar_p,
                "noise_delta": self.noise_delta,
                "ledger_sha": self.ledger_sha,
                "scored": self.scored,
                "generated_at": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            },
            indent=2,
            sort_keys=True,
        )


def run_ab(
    seeds: list[Seed],
    *,
    frozen_ledger: Path,
    work_root: Path,
    run_workflow_fn: RunWorkflow,
) -> ABVerdict:
    """Powered paired A/B over the admitted seeds → killable verdict.

    Scores ON and OFF on byte-identical seed diffs against per-arm copies of the
    frozen ledger (asserting the SHA never drifts across the scored set), then
    computes Fisher one-sided + McNemar exact + paired delta CI.  PROCEED iff
    delta>=+0.20 AND the 95% CI excludes 0; KILL on delta<=0 / CI spans 0;
    KEEP-DEFERRED on the narrow remaining ambiguity.
    """
    frozen_sha = ledger_sha(frozen_ledger)
    on_outcomes: list[int] = []
    off_outcomes: list[int] = []
    on_noise = off_noise = 0
    scored: list[dict[str, Any]] = []

    for seed in seeds:
        on = score_arm(
            "ON", seed, frozen_ledger=frozen_ledger, work_root=work_root,
            run_workflow_fn=run_workflow_fn, expected_ledger_sha=frozen_sha,
        )
        off = score_arm(
            "OFF", seed, frozen_ledger=frozen_ledger, work_root=work_root,
            run_workflow_fn=run_workflow_fn, expected_ledger_sha=frozen_sha,
        )
        on_outcomes.append(int(on.caught))
        off_outcomes.append(int(off.caught))
        on_noise += on.noise
        off_noise += off.noise
        scored.append(
            {
                "seed": seed.name,
                "on_caught": on.caught,
                "off_caught": off.caught,
                "on_review_sha": on.review_sha,
                "off_review_sha": off.review_sha,
                "ledger_sha": on.ledger_sha,
            }
        )

    table = ab_stats.paired_table(on_outcomes, off_outcomes)
    # Catch/miss contingency for Fisher: [[ON caught, ON missed],[OFF caught, OFF missed]].
    n = len(on_outcomes)
    on_caught = sum(on_outcomes)
    off_caught = sum(off_outcomes)
    fisher_p = ab_stats.fisher_exact_one_sided(
        [[on_caught, n - on_caught], [off_caught, n - off_caught]]
    ) if n else 1.0
    mcnemar_p = ab_stats.mcnemar_exact(table, one_sided=True)
    ci = ab_stats.catch_rate_delta_ci(on_outcomes, off_outcomes)
    noise_delta = (on_noise - off_noise) / n if n else 0.0

    verdict = _decide(ci, mcnemar_p)
    return ABVerdict(
        verdict=verdict,
        catch_rate_on=ci.catch_rate_on,
        catch_rate_off=ci.catch_rate_off,
        delta=ci.delta,
        ci_low=ci.ci_low,
        ci_high=ci.ci_high,
        fisher_p=fisher_p,
        mcnemar_p=mcnemar_p,
        noise_delta=noise_delta,
        scored=scored,
        ledger_sha=frozen_sha,
    )


def _decide(ci: ab_stats.DeltaCI, mcnemar_p: float) -> str:
    """Kill-or-proceed decision from the paired delta CI (PROCEED bar +0.20)."""
    if ci.delta <= 0.0 or ci.ci_low <= 0.0:
        return "KILL"
    if ci.delta >= PROCEED_DELTA and ci.ci_low > 0.0:
        return "PROCEED"
    return "KEEP-DEFERRED"

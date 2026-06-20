"""Pure-logic tests for the A/B driver (Task 10) with a MOCKED Archon seam.

No live Archon run, no model call.  ``run_workflow`` is replaced by a fixture
that returns canned ``review.json`` files keyed on (arm, seed); the real
adapter+miner path seeds a frozen ledger in a temp HOME so provenance verifies.

Coverage:
  (a) frozen-ledger SHA unchanged across all scored cases (train/test split);
  (b) a SATURATED fixture set (OFF catch-rate ~1.0) -> INCONCLUSIVE;
  (c) a synthetic ON==OFF dataset -> verdict KILL (negative reportable);
  (d) ON-blind (no ticket selected) -> fails LOUD;
  (e) Fisher / McNemar computed correctly on a known 2x2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parents[2]
sys.path.insert(0, str(_THIS_DIR))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import ab_stats  # noqa: E402
import archon_ab_driver as drv  # noqa: E402

_GOLDEN_CLASS = "off-by-one"


def _review(caught: bool, golden_file: str, *, noise: int = 0) -> dict[str, object]:
    """Canned review.json: a golden P1 catch (or not) plus N P2 noise findings."""
    findings: list[dict[str, object]] = []
    if caught:
        findings.append(
            {"severity": "P1", "title": "off by one", "detail": "d",
             "file": golden_file, "class": _GOLDEN_CLASS}
        )
    for i in range(noise):
        findings.append(
            {"severity": "P2", "title": f"nit{i}", "detail": "n",
             "file": f"n{i}.py", "class": "doc-drift"}
        )
    return {"reviewer": "claude", "verdict": "REJECT", "findings": findings}


def _make_seed(tmp_path: Path, name: str, golden_file: str = "src/stage_b.py") -> drv.Seed:
    diff = tmp_path / f"{name}.diff"
    diff.write_text(f"--- diff for {name}\n")
    return drv.Seed(
        name=name, diff_path=diff, golden_class=_GOLDEN_CLASS,
        golden_file=golden_file, scope=[golden_file],
    )


def _mock_workflow(
    outcomes: dict[tuple[str, str], dict[str, object]],
    work_root: Path,
) -> Callable[[str, drv.Seed, Path], drv.WorkflowResult]:
    """Return a run_workflow stub that writes the canned review.json for (arm, seed)."""
    def _fn(arm: str, seed: drv.Seed, arm_dir: Path) -> drv.WorkflowResult:
        review = outcomes[(arm, seed.name)]
        review_path = arm_dir / "review.json"
        review_path.write_text(json.dumps(review, indent=2))
        return drv.WorkflowResult(review_path=review_path, learnings_path=None)
    return _fn


@pytest.fixture()
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Seed a frozen, promotable stage-A ledger in an isolated temp HOME."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    ledger = tmp_path / "frozen-ledger"
    verdict = drv.seed_frozen_ledger(
        repo_root, ledger, defect_class=_GOLDEN_CLASS, defect_file="src/stage_b.py",
    )
    assert verdict["promotable_count"] >= 1
    return {"home": home, "repo_root": repo_root, "ledger": ledger}


# --- (a) frozen-ledger SHA unchanged across all scored cases -----------------
def test_frozen_ledger_sha_unchanged_across_scored_cases(
    seeded: dict[str, Path], tmp_path: Path
) -> None:
    frozen = seeded["ledger"]
    before = drv.ledger_sha(frozen)
    seeds = [_make_seed(tmp_path, f"s{i}") for i in range(3)]
    work = tmp_path / "work"
    outcomes: dict[tuple[str, str], dict[str, object]] = {}
    for s in seeds:
        outcomes[("ON", s.name)] = _review(True, s.golden_file)
        outcomes[("OFF", s.name)] = _review(False, s.golden_file)
    fn = _mock_workflow(outcomes, work)

    verdict = drv.run_ab(seeds, frozen_ledger=frozen, work_root=work, run_workflow_fn=fn)
    # every scored row logged the SAME frozen ledger SHA
    assert {row["ledger_sha"] for row in verdict.scored} == {before}
    # the on-disk frozen ledger is itself untouched
    assert drv.ledger_sha(frozen) == before
    assert verdict.ledger_sha == before


def test_score_arm_detects_ledger_mutation(seeded: dict[str, Path], tmp_path: Path) -> None:
    """If a stray write mutates the per-arm ledger, score_arm fails loud."""
    frozen = seeded["ledger"]
    seed = _make_seed(tmp_path, "mut")
    work = tmp_path / "work"

    def _mutating(arm: str, s: drv.Seed, arm_dir: Path) -> drv.WorkflowResult:
        # simulate mining accidentally left ON: drop a new ticket into the arm ledger
        (arm_dir / "ledger" / "rogue.json").write_text("{}")
        rp = arm_dir / "review.json"
        rp.write_text(json.dumps(_review(True, s.golden_file)))
        return drv.WorkflowResult(review_path=rp, learnings_path=None)

    with pytest.raises(AssertionError, match="scoring ledger mutated"):
        drv.score_arm(
            "OFF", seed, frozen_ledger=frozen, work_root=work,
            run_workflow_fn=_mutating, expected_ledger_sha=drv.ledger_sha(frozen),
        )


# --- (b) saturated fixtures -> INCONCLUSIVE ----------------------------------
def test_saturated_pilot_inconclusive(seeded: dict[str, Path], tmp_path: Path) -> None:
    """OFF catch-rate ~1.0 for every seed -> no mid-band diff -> INCONCLUSIVE."""
    frozen = seeded["ledger"]
    seeds = [_make_seed(tmp_path, f"sat{i}") for i in range(4)]
    work = tmp_path / "work"
    outcomes: dict[tuple[str, str], dict[str, object]] = {}
    for s in seeds:
        outcomes[("OFF", s.name)] = _review(True, s.golden_file)   # OFF already catches
        outcomes[("ON", s.name)] = _review(True, s.golden_file)
    fn = _mock_workflow(outcomes, work)

    pilot = drv.run_pilot(seeds, frozen_ledger=frozen, work_root=work, run_workflow_fn=fn)
    assert pilot.verdict == "INCONCLUSIVE"
    assert pilot.admitted == []
    assert "band" in pilot.reason


def test_pilot_proceeds_with_headroom_and_discordance(
    seeded: dict[str, Path], tmp_path: Path
) -> None:
    """Mid-band OFF rate + OFF-miss->ON-catch on >=2 pairs -> PROCEED."""
    frozen = seeded["ledger"]
    # 4 seeds; OFF catches exactly 2 of 4 across repeats=1 -> we need per-seed mid-band,
    # so use repeats=2 with an alternating OFF outcome to land at 0.5.
    seeds = [_make_seed(tmp_path, f"hd{i}") for i in range(2)]
    work = tmp_path / "work"
    # Per call OFF flips caught/missed -> over repeats=2 the rate is 0.5 (in band).
    flip: dict[str, int] = {}

    def _fn(arm: str, s: drv.Seed, arm_dir: Path) -> drv.WorkflowResult:
        rp = arm_dir / "review.json"
        if arm == "ON":
            rp.write_text(json.dumps(_review(True, s.golden_file)))
        else:
            n = flip.get(s.name, 0)
            flip[s.name] = n + 1
            rp.write_text(json.dumps(_review(n % 2 == 0, s.golden_file)))
        return drv.WorkflowResult(review_path=rp, learnings_path=None)

    pilot = drv.run_pilot(
        seeds, frozen_ledger=frozen, work_root=work, run_workflow_fn=_fn, repeats=2,
    )
    assert pilot.verdict == "PROCEED"
    assert set(pilot.admitted) == {"hd0", "hd1"}
    assert pilot.discordant_classes[_GOLDEN_CLASS] >= drv.MIN_DISCORDANT_PAIRS


# --- (c) ON==OFF dataset -> KILL ---------------------------------------------
def test_on_equals_off_kills(seeded: dict[str, Path], tmp_path: Path) -> None:
    """When ON and OFF catch identically, delta==0 -> verdict KILL."""
    frozen = seeded["ledger"]
    seeds = [_make_seed(tmp_path, f"eq{i}") for i in range(6)]
    work = tmp_path / "work"
    outcomes: dict[tuple[str, str], dict[str, object]] = {}
    for i, s in enumerate(seeds):
        same = i % 2 == 0  # identical outcome for both arms
        outcomes[("ON", s.name)] = _review(same, s.golden_file)
        outcomes[("OFF", s.name)] = _review(same, s.golden_file)
    fn = _mock_workflow(outcomes, work)

    verdict = drv.run_ab(seeds, frozen_ledger=frozen, work_root=work, run_workflow_fn=fn)
    assert verdict.verdict == "KILL"
    assert verdict.delta == pytest.approx(0.0)


def test_strong_effect_proceeds(seeded: dict[str, Path], tmp_path: Path) -> None:
    """ON catches all, OFF catches none -> delta=+1.0, CI excludes 0 -> PROCEED."""
    frozen = seeded["ledger"]
    seeds = [_make_seed(tmp_path, f"eff{i}") for i in range(8)]
    work = tmp_path / "work"
    outcomes: dict[tuple[str, str], dict[str, object]] = {}
    for s in seeds:
        outcomes[("ON", s.name)] = _review(True, s.golden_file)
        outcomes[("OFF", s.name)] = _review(False, s.golden_file)
    fn = _mock_workflow(outcomes, work)

    verdict = drv.run_ab(seeds, frozen_ledger=frozen, work_root=work, run_workflow_fn=fn)
    assert verdict.verdict == "PROCEED"
    assert verdict.delta == pytest.approx(1.0)
    assert verdict.ci_low > 0.0
    # verdict.json is recomputable / valid JSON
    parsed = json.loads(verdict.to_json())
    assert parsed["verdict"] == "PROCEED"
    assert parsed["catch_rate_on"] == 1.0


# --- (d) ON-blind guard fails loud -------------------------------------------
def test_on_blind_guard_fails_loud(seeded: dict[str, Path], tmp_path: Path) -> None:
    """ON arm with a scope that matches NO ticket -> AssertionError (not silent)."""
    frozen = seeded["ledger"]
    # scope points at a file the seeded ticket never references
    seed = drv.Seed(
        name="blind", diff_path=tmp_path / "b.diff", golden_class=_GOLDEN_CLASS,
        golden_file="src/unrelated.py", scope=["src/unrelated.py"],
    )
    seed.diff_path.write_text("x")
    work = tmp_path / "work"
    outcomes = {("ON", "blind"): _review(True, "src/unrelated.py")}
    fn = _mock_workflow(outcomes, work)

    with pytest.raises(AssertionError, match="ON-arm blind"):
        drv.score_arm(
            "ON", seed, frozen_ledger=frozen, work_root=work,
            run_workflow_fn=fn, expected_ledger_sha=drv.ledger_sha(frozen),
        )


def test_inject_command_off_inlines_env_only() -> None:
    """OFF arm prefixes the env var INLINE on the command; ON arm does not."""
    on = drv.inject_command(
        "ON", repo_root=Path("/r"), ledger_dir=Path("/l"),
        dest_dir=Path("/d"), scope=["a.py"], python_bin="python3",
    )
    off = drv.inject_command(
        "OFF", repo_root=Path("/r"), ledger_dir=Path("/l"),
        dest_dir=Path("/d"), scope=["a.py"], python_bin="python3",
    )
    assert "AUTO_PILOT_DISABLE_LEARNINGS=1" not in on
    assert off.startswith("AUTO_PILOT_DISABLE_LEARNINGS=1 ")
    assert "--sanitized" in on and "--sanitized" in off
    assert "--ledger-dir /l" in on
    # arms differ in EXACTLY the env-var prefix
    assert off == f"AUTO_PILOT_DISABLE_LEARNINGS=1 {on}"


def test_inject_command_rejects_unknown_arm() -> None:
    with pytest.raises(ValueError, match="unknown arm"):
        drv.inject_command(
            "MAYBE", repo_root=Path("/r"), ledger_dir=Path("/l"),
            dest_dir=Path("/d"), scope=[],
        )


# --- (e) Fisher / McNemar on a known 2x2 -------------------------------------
def test_fisher_exact_known_table() -> None:
    """Fisher one-sided on the canonical lady-tasting-tea 2x2 [[3,1],[1,3]].

    The classic exact one-sided p for this table is 17/70 ~= 0.2429.
    """
    p = ab_stats.fisher_exact_one_sided([[3, 1], [1, 3]])
    assert p == pytest.approx(17.0 / 70.0, abs=1e-9)


def test_fisher_perfect_separation() -> None:
    """[[4,0],[0,4]] one-sided p = 1/70 ~= 0.0142857."""
    p = ab_stats.fisher_exact_one_sided([[4, 0], [0, 4]])
    assert p == pytest.approx(1.0 / 70.0, abs=1e-9)


def test_mcnemar_exact_known_discordant() -> None:
    """McNemar exact one-sided on b=5, c=0 -> P(X>=5 | n=5, .5) = 1/32."""
    table = ab_stats.PairedOutcome(a=0, b=5, c=0, d=0)
    p = ab_stats.mcnemar_exact(table, one_sided=True)
    assert p == pytest.approx(1.0 / 32.0, abs=1e-9)


def test_mcnemar_balanced_discordant() -> None:
    """b=c -> one-sided p = P(X>=b | 2b, .5) = exactly 0.5 + half the central mass.

    For b=c=2 (n=4): P(X>=2) = 1 - P(X<=1) = 1 - (1+4)/16 = 11/16.
    """
    table = ab_stats.PairedOutcome(a=1, b=2, c=2, d=1)
    p = ab_stats.mcnemar_exact(table, one_sided=True)
    assert p == pytest.approx(11.0 / 16.0, abs=1e-9)


def test_mcnemar_no_discordant_is_one() -> None:
    table = ab_stats.PairedOutcome(a=3, b=0, c=0, d=3)
    assert ab_stats.mcnemar_exact(table) == 1.0


def test_paired_table_counts() -> None:
    on = [1, 1, 0, 0, 1]
    off = [1, 0, 1, 0, 0]
    t = ab_stats.paired_table(on, off)
    assert (t.a, t.b, t.c, t.d) == (1, 2, 1, 1)
    assert t.n == 5 and t.discordant == 3


def test_delta_ci_excludes_zero_on_strong_effect() -> None:
    on = [1] * 8
    off = [0] * 8
    ci = ab_stats.catch_rate_delta_ci(on, off)
    assert ci.delta == pytest.approx(1.0)
    # zero variance in the paired diffs -> degenerate CI at the point estimate
    assert ci.ci_low == pytest.approx(1.0)
    assert ci.ci_high == pytest.approx(1.0)


def test_delta_ci_spans_zero_on_noise() -> None:
    on = [1, 0, 1, 0, 1, 0]
    off = [0, 1, 0, 1, 0, 1]
    ci = ab_stats.catch_rate_delta_ci(on, off)
    assert ci.delta == pytest.approx(0.0)
    assert ci.ci_low < 0.0 < ci.ci_high


def test_paired_table_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        ab_stats.paired_table([1, 0], [1])

"""Live end-to-end verification for the headless driver.

Unlike test_headless_loop.py (which mocks run_claude_session / parse_session_usage),
these tests drive the REAL path with no test-double on the loop seams:

  - a fake `claude` binary (a stdlib python script) set via CLAUDE_BIN spawns as a
    real subprocess, emits a real ``{"type":"result",...}`` line, and mutates a real
    state.json the way a PM session would;
  - a real git repo backs git_head() and the recovery / apply-to-main paths;
  - usage is parsed from the real session log, accumulated, and the real budget caps
    decide termination.

Covers the three previously-unverified live paths:
  1. PM phase state machine — phase 1 -> 2 -> 3 -> success across real iterations.
  2. cost-cap — accumulation from parsed usage AND from the fail-closed estimate.
  3. crash-recovery mid-apply — a genuinely interrupted ``git am`` cleared with HEAD
     + worktree integrity, and apply_to_main self-healing a stale am-state.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
}


def _git(repo: Path, *args: str) -> str:
    env = os.environ.copy()
    env.update(GIT_ENV)
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True, env=env,
    ).stdout


def _init_repo(path: Path) -> str:
    """Init a git repo at *path* with one commit; return the base SHA."""
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q", "-b", "main")
    (path / ".gitignore").write_text(".planning/\n")
    (path / "f.txt").write_text("base\n")
    _git(path, "add", ".gitignore", "f.txt")
    _git(path, "commit", "-q", "-m", "init")
    return _git(path, "rev-parse", "HEAD").strip()


# Fake `claude -p` binary. Reads the loop-assigned phase from its prompt argv
# ("... phase N." rendered from iteration.md) so phase_for_next_session's output
# actually drives advancement — a sidecar counter is only a fallback. Completes
# that phase in state.json, preserves cost_usd/tokens, prints a result line
# unless FAKE_CLAUDE_NO_USAGE=1.
_FAKE_CLAUDE = textwrap.dedent(
    '''\
    #!/usr/bin/env python3
    import json, os, re, sys
    from pathlib import Path
    sd = Path(".planning/auto-pilot")
    state_path = sd / "state.json"
    counter_path = sd / "fake-claude-counter"
    state = json.loads(state_path.read_text())
    total = int(state.get("total_phases", 1))
    m = re.search(r"phase (\\d+)", " ".join(sys.argv))
    if m:
        p = min(int(m.group(1)), total)
    else:
        try:
            p = min(int(counter_path.read_text().strip()), total)
        except (OSError, ValueError):
            p = 1
    phases = [
        {"phase": i, "status": "success", "round": 1,
         "started": "2026-06-13T00:00:00+00:00",
         "ended": "2026-06-13T00:01:00+00:00", "commits": []}
        for i in range(1, p + 1)
    ]
    state["current_phase"] = p
    state["phases"] = phases
    state["status"] = "success" if p >= total else "running"
    tmp = state_path.with_name("state.json.tmp")
    tmp.write_text(json.dumps(state))
    os.replace(tmp, state_path)
    counter_path.write_text(str(p + 1))
    if os.environ.get("FAKE_CLAUDE_NO_USAGE") != "1":
        cost = float(os.environ.get("FAKE_CLAUDE_COST", "1.0"))
        print(json.dumps({"type": "result", "total_cost_usd": cost,
                          "usage": {"input_tokens": 10, "output_tokens": 20}}))
    sys.exit(0)
    '''
)


def _write_fake_claude(tmp_path: Path) -> Path:
    fake = tmp_path / "fake-claude"
    fake.write_text(_FAKE_CLAUDE)
    fake.chmod(0o755)
    return fake


def _write_state(state_dir: Path, total_phases: int) -> None:
    (state_dir / "state.json").write_text(json.dumps({
        "status": "running",
        "current_phase": 1,
        "total_phases": total_phases,
        "cost_usd": 0.0,
        "tokens": 0,
    }))


def _load_loop_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Reload headless_loop bound to tmp_path with CLAUDE_BIN -> fake binary.

    CONFIG (hence CLAUDE_BIN) and ROOT are captured at import time, so the env
    var must be set and the cwd switched BEFORE the module is (re)loaded.
    """
    fake = _write_fake_claude(tmp_path)
    monkeypatch.setenv("CLAUDE_BIN", str(fake))
    monkeypatch.chdir(tmp_path)
    sys.modules.pop("headless_loop", None)
    spec = importlib.util.spec_from_file_location(
        "headless_loop", REPO / "scripts" / "headless-loop.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.CLAUDE_BIN == str(fake), "CLAUDE_BIN seam did not bind the fake"
    return mod


@pytest.fixture()
def e2e(tmp_path, monkeypatch):
    """Real git repo + real fake-claude subprocess + reloaded loop module."""
    _init_repo(tmp_path)
    state_dir = tmp_path / ".planning" / "auto-pilot"
    state_dir.mkdir(parents=True)
    mod = _load_loop_module(tmp_path, monkeypatch)
    return mod, state_dir


# ----------------------------------------------------------------------------
# 1. PM phase state machine — live advance to success
# ----------------------------------------------------------------------------

def test_e2e_phase_machine_advances_to_success(e2e):
    """Real subprocess + real git: phases 1->2->3->success, main() returns 0."""
    mod, state_dir = e2e
    _write_state(state_dir, total_phases=3)

    rc = mod.main(["--max-iter", "10", "--sleep", "0", "--max-cost-usd", "100"])

    assert rc == 0
    final = json.loads((state_dir / "state.json").read_text())
    assert final["status"] == "success"
    assert final["current_phase"] == 3
    assert [p["phase"] for p in final["phases"]] == [1, 2, 3]
    # usage ledger recorded one record per executed session (3 phases).
    ledger = (mod.LOG_DIR / "usage.jsonl").read_text().splitlines()
    assert len(ledger) == 3
    assert [json.loads(r)["phase"] for r in ledger] == [1, 2, 3]


def test_e2e_phase_logs_written_per_iteration(e2e):
    """Each real session tees its output to a per-iter/phase log file."""
    mod, state_dir = e2e
    _write_state(state_dir, total_phases=2)

    mod.main(["--max-iter", "10", "--sleep", "0", "--max-cost-usd", "100"])

    logs = sorted(p.name for p in mod.LOG_DIR.glob("iter-*-phase-*.log"))
    assert logs == ["iter-0001-phase-1.log", "iter-0002-phase-2.log"]
    # the real result line reached the log (proves the fake subprocess streamed).
    assert '"type": "result"' in (mod.LOG_DIR / "iter-0001-phase-1.log").read_text()


# ----------------------------------------------------------------------------
# 2. cost-cap — real spend accounting
# ----------------------------------------------------------------------------

def test_e2e_cost_cap_trips_from_parsed_usage(e2e, monkeypatch):
    """Cost parsed from the real session log accumulates and trips the cap."""
    mod, state_dir = e2e
    monkeypatch.setenv("FAKE_CLAUDE_COST", "1.0")
    _write_state(state_dir, total_phases=5)  # high enough that cap, not success, ends it

    rc = mod.main([
        "--max-iter", "10", "--sleep", "0",
        "--max-cost-usd", "0.5", "--per-iter-cost-estimate", "0.01",
    ])

    assert rc == 1  # non-success terminal
    final = json.loads((state_dir / "state.json").read_text())
    assert final["status"] == "cost-cap"
    # one session ran (cost 1.0 > 0.5), then iter 2 early-exited on the cap.
    assert final["current_phase"] == 1
    assert final["cost_usd"] == pytest.approx(1.0)


def test_e2e_cost_cap_failclosed_via_estimate(e2e, monkeypatch):
    """No usage line in the log -> the per-iter estimate substitutes (never 0),
    accumulates, and still trips the cap (OBS3 fail-closed)."""
    mod, state_dir = e2e
    monkeypatch.setenv("FAKE_CLAUDE_NO_USAGE", "1")
    _write_state(state_dir, total_phases=10)

    rc = mod.main([
        "--max-iter", "20", "--sleep", "0",
        "--max-cost-usd", "0.5", "--per-iter-cost-estimate", "0.3",
    ])

    assert rc == 1
    final = json.loads((state_dir / "state.json").read_text())
    assert final["status"] == "cost-cap"
    # estimate 0.3/iter: after iter1 cost=0.3 (<0.5, runs iter2 -> 0.6), iter3 trips.
    assert final["cost_usd"] == pytest.approx(0.6)
    ledger = (mod.LOG_DIR / "usage.jsonl").read_text().splitlines()
    assert all(json.loads(r)["source"] == "estimate" for r in ledger)
    assert all(json.loads(r)["cost_usd"] == pytest.approx(0.3) for r in ledger)


# ----------------------------------------------------------------------------
# 3. crash-recovery mid-apply — genuine interrupted git am
# ----------------------------------------------------------------------------

def _leave_real_stale_am(repo: Path, base: str) -> str:
    """Start a conflicting ``git am`` and leave it interrupted (do NOT abort).

    Returns the HEAD SHA at the time the am was interrupted.
    """
    # Commit on main that changes f.txt -> guarantees a conflict against a
    # base-derived patch that also changes f.txt.
    (repo / "f.txt").write_text("main-change\n")
    _git(repo, "commit", "-q", "-am", "main change")
    head_before = _git(repo, "rev-parse", "HEAD").strip()

    # Build a conflicting patch from a base-rooted branch.
    _git(repo, "checkout", "-q", "-b", "feature", base)
    (repo / "f.txt").write_text("feature-change\n")
    _git(repo, "commit", "-q", "-am", "feature change")
    # Write the mbox OUTSIDE the repo — an untracked file inside it would
    # (correctly) trip _is_dirty and mask the path under test.
    mbox = repo.parent / "feature.mbox"
    mbox.write_text(_git(repo, "format-patch", f"{base}..feature", "--stdout"))

    # Back on main, apply -> the patch context (base "base\n") no longer matches
    # main's "main-change\n", so a plain `git am` stops with "does not apply" and
    # leaves a REAL, uniformly-abortable .git/rebase-apply. (Plain am, not --3way:
    # a 3way merge-conflict leftover is git-version-dependent in whether `git am
    # --abort` clears it; the apply-failure session is not.)
    _git(repo, "checkout", "-q", "main")
    env = os.environ.copy()
    env.update(GIT_ENV)
    res = subprocess.run(
        ["git", "-C", str(repo), "am", str(mbox)],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode != 0, "am was expected to conflict"
    assert (repo / ".git" / "rebase-apply").exists(), "no real am state was left"
    return head_before


def test_e2e_recovery_clears_real_interrupted_git_am(tmp_path):
    """run_recovery aborts a genuine interrupted am and restores HEAD + clean tree."""
    import _recover  # noqa: PLC0415

    repo = tmp_path / "repo"
    base = _init_repo(repo)
    state_dir = tmp_path / "state"
    head_before = _leave_real_stale_am(repo, base)

    result = _recover.run_recovery(repo_root=repo, state_dir=state_dir)

    assert result["stale_am_cleared"] is True
    assert result["stale_am_error"] is None
    assert not (repo / ".git" / "rebase-apply").exists()
    # HEAD restored to the pre-am commit; working tree clean (no conflict markers).
    assert _git(repo, "rev-parse", "HEAD").strip() == head_before
    assert _git(repo, "status", "--porcelain").strip() == ""
    assert (repo / "f.txt").read_text() == "main-change\n"

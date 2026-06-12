from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import _dispatch  # noqa: E402
import codex_review_bounded as crb  # noqa: E402

FAST_YAML = """\
schema_version: 1
verifier_min_tier: opus
agent_model_rank: {fable: 0, opus: 1, sonnet: 3, haiku: 4}
codex:
  effort_by_risk_tier: {none: low, low: low, medium: medium, high: high, critical: xhigh}
  timeout_s: 1
  retry_timeout_s: 1
"""

BROKEN_YAML = "codex: oops\n"


@pytest.fixture
def env(tmp_path):
    out_dir = tmp_path / "outputs" / "codex-reviewer"
    diff = tmp_path / "frozen.diff"
    diff.write_text("diff --git a/x.py b/x.py\n")
    prompt = tmp_path / "prompt.txt"
    prompt.write_text("review this")
    config = tmp_path / "routing.yaml"
    config.write_text(FAST_YAML)
    ticket = tmp_path / "ticket.json"
    ticket.write_text(json.dumps({
        "contract_id": "iter-1/phase-1/contract-1/round-1",
        "output_dir": str(out_dir),
        "diff_path": str(diff),
    }))
    return {"ticket": ticket, "prompt": prompt, "config": config, "out": out_dir}


def _run(env, codex_cmd: str, tier: str = "medium") -> int:
    return crb.main([
        "--ticket", str(env["ticket"]), "--tier", tier,
        "--prompt-file", str(env["prompt"]), "--config", str(env["config"]),
        "--codex-cmd", codex_cmd,
    ])


def test_build_argv_hardcodes_sandbox_and_effort():
    argv = crb.build_argv("high")
    assert "--sandbox" in argv and "read-only" in argv
    assert "model_reasoning_effort=high" in " ".join(argv)


def test_success_path_saves_raw_and_exits_zero(env):
    rc = _run(env, "cat")  # echoes the prompt back, exits 0
    assert rc == 0
    raw = env["out"] / "codex-raw-attempt-1.json"
    assert raw.exists() and "review this" in raw.read_text()
    assert not (env["out"] / "review.json").exists()


def test_timeout_retries_then_writes_abstain(env):
    rc = _run(env, "sleep 30")
    assert rc == 3
    review = json.loads((env["out"] / "review.json").read_text())
    assert review["verdict"] == "ABSTAIN"
    assert review["scope_check"] == "SKIPPED"
    assert review["reviewer_meta"]["abstain_reason"] == "codex-timeout"
    assert review["reviewer_meta"]["risk_tier"] == "medium"
    assert review["contract_id"] == "iter-1/phase-1/contract-1/round-1"
    status = json.loads((env["out"] / "status.json").read_text())
    assert status["phase"] == "abstained:codex-timeout"  # terminal beat
    assert review["reviewer_meta"]["effort"] == "low"  # medium downgraded once


def test_abstain_review_is_schema_valid(env):
    _run(env, "sleep 30")
    _dispatch.read_review(env["out"] / "review.json")  # no raise


def test_retry_downgrades_effort(env):
    _run(env, "sleep 30", tier="critical")  # xhigh -> retry at high
    review = json.loads((env["out"] / "review.json").read_text())
    assert review["reviewer_meta"]["effort"] == "high"
    assert review["reviewer_meta"]["risk_tier"] == "critical"


def test_exec_failure_abstains_with_exec_reason(env):
    rc = _run(env, "false")
    assert rc == 3
    review = json.loads((env["out"] / "review.json").read_text())
    assert review["reviewer_meta"]["abstain_reason"] == "codex-exec-failed"


def test_missing_ticket_is_usage_error(env, tmp_path):
    rc = crb.main(["--ticket", str(tmp_path / "absent.json"), "--tier", "low",
                   "--prompt-file", str(env["prompt"]),
                   "--config", str(env["config"]), "--codex-cmd", "cat"])
    assert rc == 2


def test_broken_config_is_usage_error(env, tmp_path):
    bad_config = tmp_path / "bad.yaml"
    bad_config.write_text(BROKEN_YAML)
    rc = crb.main([
        "--ticket", str(env["ticket"]), "--tier", "medium",
        "--prompt-file", str(env["prompt"]),
        "--config", str(bad_config),
        "--codex-cmd", "cat",
    ])
    assert rc == 2

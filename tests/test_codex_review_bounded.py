from __future__ import annotations

import json
import os
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
    assert crb.build_argv("high") == [
        "codex", "exec", "--sandbox", "read-only", "--json",
        "-c", "model_reasoning_effort=high",
        "--prompt-file", "-",
    ]


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
    assert review["verify_rerun"]["exit_code"] == 1  # `false` exits 1, not 124


def test_timeout_abstain_exit_code_is_124(env):
    rc = _run(env, "sleep 30")
    assert rc == 3
    review = json.loads((env["out"] / "review.json").read_text())
    assert review["verify_rerun"]["exit_code"] == 124


def test_unicode_decode_error_is_usage_error(env, tmp_path):
    bad_prompt = tmp_path / "bad_prompt.bin"
    bad_prompt.write_bytes(bytes([0xFF, 0xFE, 0x00]))
    rc = crb.main([
        "--ticket", str(env["ticket"]), "--tier", "medium",
        "--prompt-file", str(bad_prompt),
        "--config", str(env["config"]),
        "--codex-cmd", "cat",
    ])
    assert rc == 2


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


# ---------------------------------------------------------------------------
# Finding 1: out_dir I/O failures honor the 0/3/2 exit contract
# ---------------------------------------------------------------------------

def test_out_dir_is_existing_file_returns_rc2(env, tmp_path):
    """out_dir path points at an existing regular file → rc 2 (not traceback)."""
    file_as_dir = tmp_path / "collision"
    file_as_dir.write_text("I am a file, not a dir")
    ticket = tmp_path / "ticket_collision.json"
    ticket.write_text(json.dumps({
        "contract_id": "iter-1/phase-1/contract-1/round-1",
        "output_dir": str(file_as_dir),
        "diff_path": str(tmp_path / "d.diff"),
    }))
    rc = crb.main([
        "--ticket", str(ticket), "--tier", "medium",
        "--prompt-file", str(env["prompt"]),
        "--config", str(env["config"]),
        "--codex-cmd", "cat",
    ])
    assert rc == 2


@pytest.mark.skipif(os.geteuid() == 0, reason="chmod 555 has no effect as root")
def test_unwritable_out_dir_parent_returns_rc2(env, tmp_path):
    """Unwritable parent dir → PermissionError → rc 2."""
    locked_parent = tmp_path / "locked"
    locked_parent.mkdir()
    out_dir = locked_parent / "outputs" / "codex-reviewer"
    ticket = tmp_path / "ticket_locked.json"
    ticket.write_text(json.dumps({
        "contract_id": "iter-1/phase-1/contract-1/round-1",
        "output_dir": str(out_dir),
        "diff_path": str(tmp_path / "d.diff"),
    }))
    locked_parent.chmod(0o555)
    try:
        rc = crb.main([
            "--ticket", str(ticket), "--tier", "medium",
            "--prompt-file", str(env["prompt"]),
            "--config", str(env["config"]),
            "--codex-cmd", "cat",
        ])
        assert rc == 2
    finally:
        locked_parent.chmod(0o755)


# ---------------------------------------------------------------------------
# Finding 2: empty / relative output_dir rejected at parse time
# ---------------------------------------------------------------------------

def _make_ticket(tmp_path: Path, out_dir_value: object) -> Path:
    t = tmp_path / "ticket_bad_outdir.json"
    t.write_text(json.dumps({
        "contract_id": "iter-1/phase-1/contract-1/round-1",
        "output_dir": out_dir_value,
        "diff_path": str(tmp_path / "d.diff"),
    }))
    return t


def test_empty_output_dir_returns_rc2(env, tmp_path):
    ticket = _make_ticket(tmp_path, "")
    rc = crb.main([
        "--ticket", str(ticket), "--tier", "medium",
        "--prompt-file", str(env["prompt"]),
        "--config", str(env["config"]),
        "--codex-cmd", "cat",
    ])
    assert rc == 2


def test_relative_output_dir_returns_rc2(env, tmp_path):
    ticket = _make_ticket(tmp_path, "relative/path")
    rc = crb.main([
        "--ticket", str(ticket), "--tier", "medium",
        "--prompt-file", str(env["prompt"]),
        "--config", str(env["config"]),
        "--codex-cmd", "cat",
    ])
    assert rc == 2


# ---------------------------------------------------------------------------
# Finding 4: attempt stderr persisted to <raw>.stderr on non-zero exit
# ---------------------------------------------------------------------------

def test_attempt_stderr_persisted_on_failure(env):
    """codex-cmd that writes to stderr and exits non-zero → .stderr sidecar."""
    rc = _run(env, "sh -c 'echo boom >&2; exit 7'")
    assert rc == 3  # ABSTAIN
    review = json.loads((env["out"] / "review.json").read_text())
    assert review["verify_rerun"]["exit_code"] == 7
    stderr_file = env["out"] / "codex-raw-attempt-1.json.stderr"
    assert stderr_file.exists(), "stderr sidecar not written"
    assert "boom" in stderr_file.read_text()


def test_timeout_does_not_write_stderr_sidecar(env):
    """On timeout there is no captured stderr — sidecar must not be written."""
    _run(env, "sleep 30")
    # Neither attempt should have a .stderr sidecar
    assert not (env["out"] / "codex-raw-attempt-1.json.stderr").exists()
    assert not (env["out"] / "codex-raw-attempt-2.json.stderr").exists()

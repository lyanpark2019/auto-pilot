"""Tests for scripts/risk_assess.py — risk-tiered review-gate classifier."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "risk_assess.py"
sys.path.insert(0, str(ROOT / "scripts"))

import risk_assess  # noqa: E402


# ---------------------------------------------------------------------------
# Tier classification table
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("path", "expected_tier"),
    [
        # critical tokens in path segments
        ("app/services/auth/login.py", "critical"),
        ("src/oauth_callback.ts", "critical"),
        ("api/payment/charge.py", "critical"),
        ("lib/session_store.py", "critical"),
        ("config/secrets.yaml", "critical"),       # plural folding: secrets→secret
        ("billing/invoice.js", "critical"),
        ("handlers/webhook.sh", "critical"),
        # high tokens
        ("app/migrations/077_replica_identity.sql", "high"),
        ("schemas/contract.schema.json", "high"),  # schema beats LOW config
        ("hooks/pre_tool_use.sh", "high"),
        ("scripts/_dispatch.py", "high"),
        ("ci/quality_gate.yml", "high"),
        # medium: plain source
        ("scripts/risk_assess.py", "medium"),
        ("deploy/run.sh", "medium"),
        ("web/src/index.ts", "medium"),
        # low: config (outside schemas/)
        ("config/settings.json", "low"),
        ("app/config.yaml", "low"),
        ("pyproject.toml", "low"),
        # none: docs / dashboard / .planning / unknown
        ("README.md", "none"),
        ("docs/architecture/overview.md", "none"),
        ("dashboard/index.js", "none"),
        (".planning/notes/scratch.py", "none"),
        ("assets/logo.png", "none"),
        # exact-token matching: no substring false positives
        ("nlp/tokenizer.py", "medium"),
        # tests count one level below their subject
        ("tests/test_build.py", "low"),            # medium subject → low
        ("tests/test_auth.py", "high"),            # critical subject → high
        ("app/tests/fixtures/sample.json", "none"),  # low subject → none
        ("web/login.spec.ts", "low"),              # .spec source → low
    ],
)
def test_classify_path_table(path: str, expected_tier: str) -> None:
    assert risk_assess.classify_path(path) == expected_tier


# ---------------------------------------------------------------------------
# assess(): aggregation, highest-wins, extra-risk
# ---------------------------------------------------------------------------

def test_mixed_paths_highest_tier_wins() -> None:
    result = risk_assess.assess(
        ["README.md", "scripts/util.py", "app/auth/login.py"]
    )
    assert result.tier == "critical"
    assert result.files == 3
    assert result.by_tier == {
        "none": 1, "low": 0, "medium": 1, "high": 0, "critical": 1
    }
    assert result.review_policy == (
        "dual-review+gatekeeper(security mode)+tight-rescope"
    )


def test_tests_only_diff_is_low() -> None:
    result = risk_assess.assess(
        ["tests/test_build.py", "tests/test_status.py"]
    )
    assert result.tier == "low"
    assert result.review_policy == "single-reviewer"


def test_empty_input_is_none_tier() -> None:
    result = risk_assess.assess([])
    assert result.tier == "none"
    assert result.files == 0
    assert result.review_policy == "skip-review"


def test_extra_risk_raises_docs_only_diff() -> None:
    result = risk_assess.assess(["README.md"], extra_risk="high")
    assert result.tier == "high"
    assert result.extra_risk == "high"
    assert result.review_policy == (
        "dual-review+gatekeeper(security mode)+tight-rescope"
    )


def test_extra_risk_never_lowers_computed_tier() -> None:
    result = risk_assess.assess(["app/auth/login.py"], extra_risk="low")
    assert result.tier == "critical"


def test_policy_map_per_tier() -> None:
    assert risk_assess.REVIEW_POLICY == {
        "none": "skip-review",
        "low": "single-reviewer",
        "medium": "dual-review",
        "high": "dual-review+gatekeeper(security mode)+tight-rescope",
        "critical": "dual-review+gatekeeper(security mode)+tight-rescope",
    }


# ---------------------------------------------------------------------------
# CLI behavior (subprocess)
# ---------------------------------------------------------------------------

def _run_cli(
    *args: str,
    stdin_text: str = "",
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
        check=False,
    )


def test_cli_argv_paths_outputs_json_and_exit_zero() -> None:
    proc = _run_cli("app/auth/login.py", "README.md")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["tier"] == "critical"
    assert payload["files"] == 2
    assert payload["by_tier"]["critical"] == 1
    assert payload["by_tier"]["none"] == 1


def test_cli_stdin_lines_mode() -> None:
    proc = _run_cli(stdin_text="scripts/a.py\ndocs/b.md\n")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["tier"] == "medium"
    assert payload["files"] == 2


def test_cli_empty_stdin_is_none_exit_zero() -> None:
    proc = _run_cli(stdin_text="")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload == {
        "tier": "none",
        "files": 0,
        "by_tier": {"none": 0, "low": 0, "medium": 0, "high": 0, "critical": 0},
        "review_policy": "skip-review",
        "extra_risk": None,
    }


def test_cli_fail_on_exits_2_when_tier_reached() -> None:
    proc = _run_cli("app/auth/login.py", "--fail-on", "critical")
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["tier"] == "critical"


def test_cli_fail_on_exits_0_below_threshold() -> None:
    proc = _run_cli("scripts/util.py", "--fail-on", "critical")
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["tier"] == "medium"


def test_cli_fail_on_high_also_trips_on_critical() -> None:
    proc = _run_cli("app/auth/login.py", "--fail-on", "high")
    assert proc.returncode == 2


def test_cli_extra_risk_flag() -> None:
    proc = _run_cli("README.md", "--extra-risk", "critical")
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["tier"] == "critical"
    assert payload["extra_risk"] == "critical"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test",
         *args],
        cwd=repo, capture_output=True, text=True, timeout=30, check=True,
    )


def test_cli_diff_range_mode_with_tmp_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("# hi\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "tag", "base")
    auth_dir = repo / "app" / "auth"
    auth_dir.mkdir(parents=True)
    (auth_dir / "login.py").write_text("x = 1\n")
    (repo / "notes.md").write_text("notes\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "change")

    proc = _run_cli("--diff-range", "base..HEAD", cwd=repo)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["tier"] == "critical"
    assert payload["files"] == 2
    assert payload["by_tier"]["critical"] == 1
    assert payload["by_tier"]["none"] == 1


def test_cli_diff_range_bad_range_exits_1(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    proc = _run_cli("--diff-range", "nope..HEAD", cwd=repo)
    assert proc.returncode == 1
    assert "failed" in proc.stderr


@pytest.mark.parametrize(
    ("path", "expected_ext"),
    [("Makefile", ""), (".env", ""), ("archive.tar.gz", "gz")],
)
def test_extension_edge_cases(path: str, expected_ext: str) -> None:
    assert risk_assess._extension(path) == expected_ext


@pytest.mark.parametrize(
    ("tier", "expected_policy"),
    [
        ("none", "skip-review"),
        ("low", "single-reviewer"),
        ("medium", "dual-review"),
        ("high", "dual-review+gatekeeper(security mode)+tight-rescope"),
        ("critical", "dual-review+gatekeeper(security mode)+tight-rescope"),
    ],
)
def test_assessment_to_json_contract(tier: str, expected_policy: str) -> None:
    assessment = risk_assess.Assessment(
        tier=tier,
        files=1,
        by_tier={name: int(name == tier) for name in risk_assess.TIERS},
        review_policy=expected_policy,
        extra_risk=None,
    )

    payload = json.loads(assessment.to_json())

    assert payload["tier"] == tier
    assert payload["review_policy"] == expected_policy


def test_changed_files_from_git_returns_non_empty_lines() -> None:
    fake = subprocess.CompletedProcess(
        args=["git"], returncode=0, stdout="a.py\n\nREADME.md\n", stderr=""
    )
    with pytest.MonkeyPatch.context() as mp:
        calls: list[dict[str, object]] = []

        def fake_run(*args, **kwargs):
            calls.append(kwargs)
            return fake

        mp.setattr(risk_assess.subprocess, "run", fake_run)
        assert risk_assess.changed_files_from_git("base..HEAD", timeout=3.5) == ["a.py", "README.md"]

    assert calls[0]["timeout"] == 3.5


def test_changed_files_from_git_raises_on_git_failure() -> None:
    fake = subprocess.CompletedProcess(
        args=["git"], returncode=128, stdout="", stderr="bad range"
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(risk_assess.subprocess, "run", lambda *args, **kwargs: fake)
        with pytest.raises(RuntimeError, match="bad range"):
            risk_assess.changed_files_from_git("bad..HEAD")


def test_main_handles_diff_range_timeout(capsys) -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            risk_assess,
            "changed_files_from_git",
            lambda _range: (_ for _ in ()).throw(subprocess.TimeoutExpired(["git"], 30)),
        )
        rc = risk_assess.main(["--diff-range", "base..HEAD"])

    assert rc == 1
    assert "risk_assess:" in capsys.readouterr().err


def test_main_reads_stdin_when_no_paths(monkeypatch, capsys) -> None:
    class FakeStdin:
        def isatty(self) -> bool:
            return False

        def __iter__(self):
            return iter(["scripts/a.py\n", "docs/b.md\n"])

    monkeypatch.setattr(risk_assess.sys, "stdin", FakeStdin())

    rc = risk_assess.main([])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["tier"] == "medium"

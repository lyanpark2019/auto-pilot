"""Tests for fail-open observability (r4 hooks-observability contract).

Each fail-open path must emit ONE structured stderr line:
    [hook:<name>] fail-open: <reason>
and still exit 0 (non-blocking by design).

Also covers gh-auth-preflight.sh cache invalidation on `gh auth switch`.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_hook(
    hook: Path,
    payload: dict,
    *,
    cwd: Path,
    env: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=full_env,
        timeout=15,
    )


def _run_hook_raw(
    hook: Path,
    raw_stdin: str,
    *,
    cwd: Path,
    env: dict | None = None,
) -> subprocess.CompletedProcess[str]:
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    return subprocess.run(
        [str(hook)],
        input=raw_stdin,
        capture_output=True,
        text=True,
        cwd=str(cwd),
        env=full_env,
        timeout=15,
    )


HOOKS_DIR = REPO_ROOT / "hooks"

# ─── branch-lock.sh ──────────────────────────────────────────────────────────


class TestBranchLockFailOpen:
    def _hook(self) -> Path:
        return HOOKS_DIR / "branch-lock.sh"

    def test_unparseable_stdin_exits_zero(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert r.returncode == 0

    def test_unparseable_stdin_emits_fail_open_marker(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert "[hook:branch-lock] fail-open:" in r.stderr


# ─── deletion-diff-guard.sh ──────────────────────────────────────────────────


class TestDeletionDiffGuardFailOpen:
    def _hook(self) -> Path:
        return HOOKS_DIR / "deletion-diff-guard.sh"

    def test_unparseable_stdin_exits_zero(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert r.returncode == 0

    def test_unparseable_stdin_emits_fail_open_marker(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert "[hook:deletion-diff-guard] fail-open:" in r.stderr


# ─── gh-auth-preflight.sh ────────────────────────────────────────────────────


class TestGhAuthPreflightFailOpen:
    def _hook(self) -> Path:
        return HOOKS_DIR / "gh-auth-preflight.sh"

    def test_unparseable_stdin_exits_zero(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert r.returncode == 0

    def test_unparseable_stdin_emits_fail_open_marker(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert "[hook:gh-auth-preflight] fail-open:" in r.stderr

    def test_gh_auth_switch_purges_cache_files(self, tmp_path: Path) -> None:
        """gh auth switch must remove all gh-auth-*.cache files before exiting."""
        tmpdir = str(tmp_path)
        cache_a = tmp_path / "gh-auth-lyanpark2019.cache"
        cache_b = tmp_path / "gh-auth-Sewhoan.cache"
        cache_a.write_text("lyanpark2019")
        cache_b.write_text("Sewhoan")

        r = _run_hook(
            self._hook(),
            {"tool_input": {"command": "gh auth switch --user lyanpark2019"}},
            cwd=tmp_path,
            env={"TMPDIR": tmpdir},
        )
        assert r.returncode == 0
        assert not cache_a.exists(), "cache file was not purged on gh auth switch"
        assert not cache_b.exists(), "cache file was not purged on gh auth switch"

    def test_gh_auth_switch_still_exits_zero(self, tmp_path: Path) -> None:
        """gh auth switch must remain non-blocking (exit 0) even after cache purge."""
        r = _run_hook(
            self._hook(),
            {"tool_input": {"command": "gh auth switch --hostname github.com"}},
            cwd=tmp_path,
            env={"TMPDIR": str(tmp_path)},
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_non_switch_gh_auth_does_not_purge_cache(self, tmp_path: Path) -> None:
        """gh auth login/status must NOT purge cache — only switch does."""
        cache = tmp_path / "gh-auth-lyanpark2019.cache"
        cache.write_text("lyanpark2019")

        r = _run_hook(
            self._hook(),
            {"tool_input": {"command": "gh auth status"}},
            cwd=tmp_path,
            env={"TMPDIR": str(tmp_path)},
        )
        assert r.returncode == 0
        # Cache file must still exist (gh auth status is not a switch)
        assert cache.exists(), "cache was incorrectly purged on gh auth status"

    def test_no_git_remote_exits_zero_with_marker(self, tmp_path: Path) -> None:
        """When repo has no git remote, owner is empty → fail-open with marker."""
        # Init a bare git repo with no remote so git remote get-url origin fails
        subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
        r = _run_hook(
            self._hook(),
            {"tool_input": {"command": "gh repo view"}},
            cwd=tmp_path,
            env={"TMPDIR": str(tmp_path)},
        )
        assert r.returncode == 0
        assert "[hook:gh-auth-preflight] fail-open:" in r.stderr

    def test_gh_unavailable_exits_zero_with_marker(self, tmp_path: Path) -> None:
        """When gh is not authenticated (returns empty), hook fails open with marker."""
        # Stub gh to exit 1 (simulates unauthenticated / unavailable)
        fake_bin = tmp_path / "fake_bin"
        fake_bin.mkdir()
        fake_gh = fake_bin / "gh"
        fake_gh.write_text("#!/usr/bin/env bash\nexit 1\n")
        fake_gh.chmod(0o755)

        # Use a remote URL that resolves owner so we pass the owner check
        git_dir = tmp_path / "myrepo"
        git_dir.mkdir()
        subprocess.run(["git", "init", str(git_dir)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(git_dir), "remote", "add", "origin",
             "https://github.com/lyanpark2019/some-repo.git"],
            check=True,
            capture_output=True,
        )

        r = _run_hook(
            self._hook(),
            {"tool_input": {"command": "gh repo view", "cwd": str(git_dir)}},
            cwd=git_dir,
            env={"TMPDIR": str(tmp_path), "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )
        assert r.returncode == 0
        assert "[hook:gh-auth-preflight] fail-open:" in r.stderr


# ─── creation-gate.sh ────────────────────────────────────────────────────────


class TestCreationGateFailOpen:
    def _hook(self) -> Path:
        return HOOKS_DIR / "creation-gate.sh"

    def test_unparseable_stdin_exits_zero(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert r.returncode == 0

    def test_unparseable_stdin_emits_fail_open_marker(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert "[hook:creation-gate] fail-open:" in r.stderr

    def test_non_creator_skill_exits_zero_with_marker(self, tmp_path: Path) -> None:
        """Non-creator Skill tool → allow_non_creator branch exits 0 with marker."""
        r = _run_hook(
            self._hook(),
            {"tool_name": "Skill", "tool_input": {"skill": "auto-pilot"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "[hook:creation-gate] fail-open:" in r.stderr


# ─── dispatch-contract-gate.sh ───────────────────────────────────────────────


class TestDispatchContractGateFailOpen:
    def _hook(self) -> Path:
        return HOOKS_DIR / "dispatch-contract-gate.sh"

    def test_unparseable_stdin_exits_zero(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert r.returncode == 0

    def test_unparseable_stdin_emits_fail_open_marker(self, tmp_path: Path) -> None:
        r = _run_hook_raw(self._hook(), "not json {{{", cwd=tmp_path)
        assert "[hook:dispatch-contract-gate] fail-open:" in r.stderr

    def test_no_phase_in_contract_emits_fail_open_marker(self, tmp_path: Path) -> None:
        """When contract.json has no phase field, the hook skips preflight and
        must emit a fail-open trace line (previously silent)."""
        contract_dir = tmp_path / "contracts"
        contract_dir.mkdir()
        contract_json = contract_dir / "contract.json"
        # Contract with no phase field — sha check will pass, then phase parse → empty
        contract_json.write_text('{"id": "some-task-without-phase"}')

        sha = subprocess.check_output(
            ["shasum", "-a", "256", str(contract_json)], text=True
        ).split()[0]
        (contract_dir / "contract-check.json").write_text(
            json.dumps({"contract_sha256": sha})
        )

        r = _run_hook(
            self._hook(),
            {"tool_name": "Task", "tool_input": {
                "prompt": f"Worker task. contract_dir={contract_dir}"
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "[hook:dispatch-contract-gate] fail-open:" in r.stderr

from __future__ import annotations
import os

import json
import subprocess
from pathlib import Path




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


def _strip_bypass(env: dict | None = None) -> dict:
    base = {"AUTO_PILOT_FORCE_COMPOSITION_ROOT": "", "AUTO_PILOT_BASH_BYPASS": ""}
    if env:
        base.update(env)
    return base


def _deny_json(stdout: str) -> dict:
    """Parse the deny JSON from hook stdout; raise if absent/malformed."""
    data = json.loads(stdout)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    return data


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestPreflightPath:
    def test_clean_cwd_silent(self, hooks_dir, tmp_path_factory):
        clean = Path.home() / ".cache" / "auto-pilot-tests"
        clean.mkdir(parents=True, exist_ok=True)
        try:
            r = _run_hook(hooks_dir / "preflight-path.sh", {}, cwd=clean)
        finally:
            try:
                clean.rmdir()
            except OSError:
                pass
        assert r.returncode == 0
        assert r.stderr == ""

    def test_tmp_cwd_warns(self, hooks_dir, in_tmp_cwd):
        r = _run_hook(hooks_dir / "preflight-path.sh", {}, cwd=in_tmp_cwd)
        assert r.returncode == 0
        assert "CWD is in" in r.stderr

    def test_running_state_emits_resume(self, hooks_dir, in_tmp_cwd):
        state_dir = in_tmp_cwd / ".planning" / "auto-pilot"
        state_dir.mkdir(parents=True)
        (state_dir / "state.json").write_text(
            json.dumps({"status": "running", "current_phase": 2})
        )
        r = _run_hook(hooks_dir / "preflight-path.sh", {}, cwd=in_tmp_cwd)
        assert r.returncode == 0
        assert "resuming session" in r.stderr
        assert "current_phase=2" in r.stderr

    def test_typo_vault_warns(self, hooks_dir, in_tmp_cwd):
        (in_tmp_cwd / "Valut").mkdir()
        r = _run_hook(hooks_dir / "preflight-path.sh", {}, cwd=in_tmp_cwd)
        assert r.returncode == 0
        assert "typo" in r.stderr


class TestPostDeployVerify:
    def test_non_deploy_is_noop(self, hooks_dir, in_tmp_cwd):
        r = _run_hook(
            hooks_dir / "post-deploy-verify.sh",
            {"tool_input": {"command": "ls -la"}},
            cwd=in_tmp_cwd,
        )
        assert r.returncode == 0
        assert r.stderr == ""

    def test_deploy_command_runs_checks(self, hooks_dir, in_tmp_cwd):
        r = _run_hook(
            hooks_dir / "post-deploy-verify.sh",
            {"tool_input": {"command": "git push origin main"}},
            cwd=in_tmp_cwd,
        )
        assert r.returncode == 0
        assert "detected deploy-class command" in r.stderr

    def test_env_placeholder_warns(self, hooks_dir, in_tmp_cwd):
        (in_tmp_cwd / ".env.production").write_text("API_KEY=REPLACE_ME\nDB_URL=postgres://x\n")
        r = _run_hook(
            hooks_dir / "post-deploy-verify.sh",
            {"tool_input": {"command": "vercel --prod"}},
            cwd=in_tmp_cwd,
        )
        assert r.returncode == 0
        assert "placeholder" in r.stderr

    def test_empty_command_passes(self, hooks_dir, in_tmp_cwd):
        r = _run_hook(
            hooks_dir / "post-deploy-verify.sh",
            {"tool_input": {}},
            cwd=in_tmp_cwd,
        )
        assert r.returncode == 0

    def test_malformed_json_warns_not_blocks(self, hooks_dir, in_tmp_cwd):
        r = subprocess.run(
            [str(hooks_dir / "post-deploy-verify.sh")],
            input="this is not json {{{",
            capture_output=True,
            text=True,
            cwd=str(in_tmp_cwd),
            timeout=15,
        )
        assert r.returncode == 0
        assert "malformed tool_input json" in r.stderr


def test_hooks_json_matcher_includes_multiedit():
    """hooks.json PreToolUse matcher for composition-root hook must cover MultiEdit."""
    hooks_json = Path(__file__).parent.parent / "hooks" / "hooks.json"
    data = json.loads(hooks_json.read_text())
    pre_tool_use = data["hooks"]["PreToolUse"]
    composition_root_entry = next(
        e for e in pre_tool_use
        if any("pre-edit-composition-root.sh" in h["command"] for h in e["hooks"])
    )
    matcher = composition_root_entry["matcher"]
    for tool in ("Edit", "Write", "MultiEdit"):
        assert tool in matcher.split("|"), f"matcher {matcher!r} missing {tool}"


def test_git_version_preflight_accepts_232():
    out = subprocess.check_output(
        ["bash", "-c",
         'v=$(git --version | awk "{print \\$3}"); '
         'IFS=. read -r maj min _ <<< "$v"; '
         '[ "$maj" -gt 2 ] || { [ "$maj" -eq 2 ] && [ "$min" -ge 32 ]; } && echo OK || echo FAIL'],
        text=True,
    ).strip()
    assert out == "OK"

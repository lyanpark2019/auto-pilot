from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


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


class TestPreEditCompositionRoot:
    def test_blocks_init_py(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": "pkg/__init__.py"}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 2
        assert "BLOCKED" in r.stderr

    @pytest.mark.parametrize(
        "path",
        ["app/composition_root.py", "src/container.py", "lib/wiring.py", "x/composition.py"],
    )
    def test_blocks_other_roots(self, hooks_dir, in_tmp_cwd, clean_env, path):
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": path}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 2

    def test_bypass_env_allows(self, hooks_dir, in_tmp_cwd):
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": "pkg/__init__.py"}},
            cwd=in_tmp_cwd,
            env={"AUTO_PILOT_FORCE_COMPOSITION_ROOT": "1"},
        )
        assert r.returncode == 0

    def test_non_root_path_passes(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": "pkg/module.py"}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 0

    def test_empty_file_path_passes(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 0

    def test_ts_barrel_warns_not_block(self, hooks_dir, in_tmp_cwd, clean_env):
        barrel = in_tmp_cwd / "index.ts"
        barrel.write_text("export * from './a';\nexport { B } from './b';\n")
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": str(barrel)}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 0
        assert "WARNING" in r.stderr

    def test_malformed_json_warns_not_blocks(self, hooks_dir, in_tmp_cwd):
        r = subprocess.run(
            [str(hooks_dir / "pre-edit-composition-root.sh")],
            input="this is not json {{{",
            capture_output=True,
            text=True,
            cwd=str(in_tmp_cwd),
            timeout=15,
        )
        assert r.returncode == 0
        assert "malformed tool_input json" in r.stderr


class TestPreBashGuard:
    def test_blocks_claude_doctor(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-bash-guard.sh",
            {"tool_input": {"command": "claude doctor"}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 2
        assert "BLOCKED" in r.stderr

    def test_blocks_ruff_fix_on_init(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-bash-guard.sh",
            {"tool_input": {"command": "ruff check --fix pkg/__init__.py"}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 2
        assert "ruff --fix" in r.stderr

    def test_ruff_fix_on_normal_file_passes(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-bash-guard.sh",
            {"tool_input": {"command": "ruff check --fix pkg/module.py"}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 0

    def test_blocks_chained_ssl(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-bash-guard.sh",
            {"tool_input": {"command": "cf set ssl_mode strict && cf set min_tls_version 1.3"}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 2
        assert "chained SSL" in r.stderr

    def test_single_ssl_passes(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-bash-guard.sh",
            {"tool_input": {"command": "cf set ssl_mode strict"}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 0

    def test_bypass_env(self, hooks_dir, in_tmp_cwd):
        r = _run_hook(
            hooks_dir / "pre-bash-guard.sh",
            {"tool_input": {"command": "claude doctor"}},
            cwd=in_tmp_cwd,
            env={"AUTO_PILOT_BASH_BYPASS": "1"},
        )
        assert r.returncode == 0

    def test_empty_command_passes(self, hooks_dir, in_tmp_cwd, clean_env):
        r = _run_hook(
            hooks_dir / "pre-bash-guard.sh",
            {"tool_input": {}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 0

    def test_malformed_json_warns_not_blocks(self, hooks_dir, in_tmp_cwd):
        r = subprocess.run(
            [str(hooks_dir / "pre-bash-guard.sh")],
            input="this is not json {{{",
            capture_output=True,
            text=True,
            cwd=str(in_tmp_cwd),
            timeout=15,
        )
        assert r.returncode == 0
        assert "malformed tool_input json" in r.stderr


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


def test_git_version_preflight_accepts_232():
    out = subprocess.check_output(
        ["bash", "-c",
         'v=$(git --version | awk "{print \\$3}"); '
         'IFS=. read -r maj min _ <<< "$v"; '
         '[ "$maj" -gt 2 ] || { [ "$maj" -eq 2 ] && [ "$min" -ge 32 ]; } && echo OK || echo FAIL'],
        text=True,
    ).strip()
    # On any modern CI the installed git is >= 2.32; expect OK
    assert out == "OK"

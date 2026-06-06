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


def _make_root(cwd: Path, rel: str, body: str = "from .x import Y\n__all__ = ['Y']\n") -> str:
    f = cwd / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body)
    return rel


class TestPreEditCompositionRoot:
    def test_blocks_init_py(self, hooks_dir, in_tmp_cwd, clean_env):
        rel = _make_root(in_tmp_cwd, "pkg/__init__.py")
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": rel}},
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
        rel = _make_root(in_tmp_cwd, path, body="container = wire()\n")
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": rel}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 2

    def test_new_init_creation_passes(self, hooks_dir, in_tmp_cwd, clean_env):
        """Creating a new (not-yet-existing) package __init__.py is not bulk-format risk."""
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": "pkg/__init__.py"}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 0

    def test_empty_existing_init_passes(self, hooks_dir, in_tmp_cwd, clean_env):
        """An empty / comment-only __init__.py has no re-exports to corrupt."""
        rel = _make_root(in_tmp_cwd, "pkg/__init__.py", body="# package marker\n\n")
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": rel}},
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 0

    def test_bypass_env_allows(self, hooks_dir, in_tmp_cwd):
        rel = _make_root(in_tmp_cwd, "pkg/__init__.py")
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {"tool_input": {"file_path": rel}},
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

    def test_handles_multiedit_input_shape(self, hooks_dir, in_tmp_cwd, clean_env):
        """When invoked via the matcher, script must extract file_path from MultiEdit input."""
        root = in_tmp_cwd / "pkg" / "__init__.py"
        root.parent.mkdir(parents=True, exist_ok=True)
        root.write_text("from .x import Y\n")
        r = _run_hook(
            hooks_dir / "pre-edit-composition-root.sh",
            {
                "tool_name": "MultiEdit",
                "tool_input": {
                    "file_path": str(root),
                    "edits": [{"old_string": "x", "new_string": "y"}],
                },
            },
            cwd=in_tmp_cwd,
            env=_strip_bypass(),
        )
        assert r.returncode == 2
        assert "BLOCKED" in r.stderr


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
    # On any modern CI the installed git is >= 2.32; expect OK
    assert out == "OK"


class TestNotebookLMDeleteGate:
    """Matcher (hooks.json) and script (notebooklm_delete_gate.sh) must block the
    same MCP tool-name set: any mcp__notebooklm__ tool with 'delete' anywhere in
    the name (suffix forms like notebook_delete were invisible to the old
    mcp__notebooklm__delete.* prefix matcher -- fail-open)."""

    MCP_DELETE_NAMES = (
        "mcp__notebooklm__delete_notebook",   # prefix form (old matcher caught)
        "mcp__notebooklm__notebook_delete",   # suffix form (old matcher MISSED)
        "mcp__notebooklm__source_delete",     # suffix form (old matcher MISSED)
    )

    def _gate(self, hooks_dir: Path) -> Path:
        return hooks_dir / "notebooklm_delete_gate.sh"

    def _matcher(self) -> str:
        hooks_json = Path(__file__).parent.parent / "hooks" / "hooks.json"
        data = json.loads(hooks_json.read_text())
        entry = next(
            e for e in data["hooks"]["PreToolUse"]
            if e["matcher"].startswith("mcp__notebooklm__")
        )
        return entry["matcher"]

    def test_matcher_covers_script_intent(self):
        import re
        matcher = re.compile(self._matcher())
        for name in self.MCP_DELETE_NAMES:
            assert matcher.search(name), f"hooks.json matcher misses {name}"

    @pytest.mark.parametrize("tool_name", MCP_DELETE_NAMES)
    def test_script_denies_mcp_delete_without_confirm(self, hooks_dir, tmp_path, tool_name):
        r = _run_hook(
            self._gate(hooks_dir),
            {"tool_name": tool_name, "tool_input": {"notebook_id": "x"}},
            cwd=tmp_path,
            env={"NBM_DELETE_CONFIRMED": "0"},
        )
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_script_allows_with_confirm_env(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._gate(hooks_dir),
            {"tool_name": "mcp__notebooklm__notebook_delete", "tool_input": {}},
            cwd=tmp_path,
            env={"NBM_DELETE_CONFIRMED": "1"},
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_script_passes_non_delete_tool(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._gate(hooks_dir),
            {"tool_name": "mcp__notebooklm__list_notebooks", "tool_input": {}},
            cwd=tmp_path,
            env={"NBM_DELETE_CONFIRMED": "0"},
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_script_denies_bash_cli_form(self, hooks_dir, tmp_path):
        # CLI literal split so this repo's own live gate hook does not fire on the test source.
        cli = "notebooklm notebook " + "delete abc"
        r = _run_hook(
            self._gate(hooks_dir),
            {"tool_name": "Bash", "tool_input": {"command": cli}},
            cwd=tmp_path,
            env={"NBM_DELETE_CONFIRMED": "0"},
        )
        assert r.returncode == 0
        out = json.loads(r.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

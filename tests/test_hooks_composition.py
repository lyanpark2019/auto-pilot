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


def _deny_json(stdout: str) -> dict:
    """Parse the deny JSON from hook stdout; raise if absent/malformed."""
    data = json.loads(stdout)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    return data


REPO_ROOT = Path(__file__).resolve().parent.parent


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

from __future__ import annotations
import os

import json
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

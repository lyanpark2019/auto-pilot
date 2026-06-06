from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

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


# ─────────────────────────────────────────────────────────────────────────────
# NEW HOOK TESTS (γ W2 round-2)
# ─────────────────────────────────────────────────────────────────────────────

def _deny_json(stdout: str) -> dict:
    """Parse the deny JSON from hook stdout; raise if absent/malformed."""
    data = json.loads(stdout)
    assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
    return data


class TestPreEditHumanOnly:
    """ⓓ-1 pre-edit-human-only.sh"""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "pre-edit-human-only.sh"

    def _make_repo(self, tmp_path: Path) -> Path:
        """Set up a minimal repo with .claude/human-only.paths."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        (claude_dir / "human-only.paths").write_text(
            "# comment\nsecret-docs/private.md\nfrozen/\n"
        )
        return tmp_path

    # ── pass cases ──

    def test_normal_file_passes(self, hooks_dir, tmp_path):
        repo = self._make_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": "src/module.py"}},
            cwd=repo,
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_new_file_no_marker_passes(self, hooks_dir, tmp_path):
        """Non-existent file (new creation) — no marker check possible → allow."""
        repo = self._make_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": "brand-new-file.py"}},
            cwd=repo,
        )
        assert r.returncode == 0

    # ── deny: human-only.paths prefix ──

    def test_denies_path_listed_in_paths_file(self, hooks_dir, tmp_path):
        repo = self._make_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": "secret-docs/private.md"}},
            cwd=repo,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_denies_prefix_match(self, hooks_dir, tmp_path):
        repo = self._make_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": "frozen/anything.py"}},
            cwd=repo,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── deny: HUMAN-ONLY marker in file ──

    def test_denies_file_with_human_only_marker(self, hooks_dir, tmp_path):
        repo = self._make_repo(tmp_path)
        target = repo / "some-file.md"
        target.write_text("# Title\nHUMAN-ONLY\nsome content\n")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": str(target)}},
            cwd=repo,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── deny: tier-2 hardcoded paths ──

    def test_denies_tier2_governance_doc(self, hooks_dir, tmp_path):
        # Tier-2 is anchored to the PLUGIN root — use an absolute plugin path
        repo = self._make_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": str(
                REPO_ROOT / "docs/specs/2026-06-06-unified-coding-system-design.md"
            )}},
            cwd=repo,
            env={"AUTO_PILOT_ALLOW_CORE_EDIT": ""},
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_denies_tier2_schemas_prefix(self, hooks_dir, tmp_path):
        repo = self._make_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": str(REPO_ROOT / "schemas/contract.schema.json")}},
            cwd=repo,
            env={"AUTO_PILOT_ALLOW_CORE_EDIT": ""},
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_denies_tier2_via_dotdot_traversal(self, hooks_dir, tmp_path):
        """`<plugin>/docs/../schemas/x` must canonicalize and still deny
        (r2: lexical compare was bypassable via ./ .. segments)."""
        repo = self._make_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": str(
                REPO_ROOT / "docs" / ".." / "schemas" / "contract.schema.json"
            )}},
            cwd=repo,
            env={"AUTO_PILOT_ALLOW_CORE_EDIT": ""},
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_allows_foreign_repo_schemas_dir(self, hooks_dir, tmp_path):
        """A target repo's own schemas/ must NOT be tier-2 denied (review r1:
        bare substring match false-denied every repo's schemas/ dir)."""
        repo = self._make_repo(tmp_path)
        (repo / "schemas").mkdir()
        (repo / "schemas" / "some-schema.json").write_text("{}")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": "schemas/some-schema.json"}},
            cwd=repo,
            env={"AUTO_PILOT_ALLOW_CORE_EDIT": ""},
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── bypass: AUTO_PILOT_ALLOW_CORE_EDIT=1 for tier-2 ──

    def test_bypass_allows_tier2_with_env(self, hooks_dir, tmp_path):
        repo = self._make_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"file_path": str(REPO_ROOT / "schemas/preflight.schema.json")}},
            cwd=repo,
            env={"AUTO_PILOT_ALLOW_CORE_EDIT": "1"},
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── malformed stdin ──

    def test_malformed_stdin_allows(self, hooks_dir, tmp_path):
        repo = self._make_repo(tmp_path)
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="not json {{{{",
            capture_output=True, text=True,
            cwd=str(repo), timeout=15,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout


class TestBranchLock:
    """ⓓ-2 branch-lock.sh"""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "branch-lock.sh"

    def _make_main_repo(self, tmp_path: Path) -> Path:
        """Init a git repo with a commit on main."""
        subprocess.run(["git", "init", "-b", "main", str(tmp_path)],
                       capture_output=True, check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@test.com"],
                       check=True)
        subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"],
                       check=True)
        (tmp_path / "README.md").write_text("test")
        subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-m", "init"],
                       capture_output=True, check=True)
        return tmp_path

    def _make_feature_repo(self, tmp_path: Path) -> Path:
        """Init a git repo on a feature branch."""
        self._make_main_repo(tmp_path)
        subprocess.run(["git", "-C", str(tmp_path), "checkout", "-b", "feature/test"],
                       capture_output=True, check=True)
        return tmp_path

    # ── pass cases ──

    def test_commit_on_feature_branch_passes(self, hooks_dir, tmp_path):
        repo = self._make_feature_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git commit -m 'test'"}},
            cwd=repo,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_non_commit_command_passes(self, hooks_dir, tmp_path):
        repo = self._make_main_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git log --oneline"}},
            cwd=repo,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── deny: commit on main ──

    def test_denies_commit_on_main(self, hooks_dir, tmp_path):
        repo = self._make_main_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git commit -m 'oops'"}},
            cwd=repo,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_denies_push_on_main(self, hooks_dir, tmp_path):
        repo = self._make_main_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git push origin main"}},
            cwd=repo,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── deny: global options must not bypass (review r1) ──

    def test_denies_commit_with_dash_C(self, hooks_dir, tmp_path):
        """`git -C <main-repo> commit` from elsewhere must still be locked."""
        repo = self._make_main_repo(tmp_path / "mainrepo")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": f"git -C {repo} commit -m 'oops'"}},
            cwd=elsewhere,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_denies_push_with_dash_c_config(self, hooks_dir, tmp_path):
        """`git -c key=val push` on main must still be locked."""
        repo = self._make_main_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git -c user.name=x push origin main"}},
            cwd=repo,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_denies_commit_with_c_before_dash_C(self, hooks_dir, tmp_path):
        """`git -c a=b -C <main-repo> commit` — -C after another global opt
        must still resolve the -C target (r2 extraction-order bypass)."""
        repo = self._make_main_repo(tmp_path / "mainrepo")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": f"git -c user.name=x -C {repo} commit -m 'oops'"}},
            cwd=elsewhere,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_denies_commit_with_dash_C_in_message(self, hooks_dir, tmp_path):
        """A `-C` token inside the commit MESSAGE must not hijack the branch
        check (r3 regression: message -C made the hook check a non-repo path
        → false-allow on main)."""
        repo = self._make_main_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git commit -m 'support -C flag'"}},
            cwd=repo,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_denies_real_dash_C_with_dash_C_in_message(self, hooks_dir, tmp_path):
        """Real `git -C <main>` plus a message mentioning `-C /tmp` — only the
        global-opts -C counts; the message token must not override it."""
        repo = self._make_main_repo(tmp_path / "mainrepo")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": f"git -C {repo} commit -m 'note -C /tmp here'"}},
            cwd=elsewhere,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── bypass ──

    def test_bypass_allows_commit_on_main(self, hooks_dir, tmp_path):
        repo = self._make_main_repo(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git commit -m 'bypass'"}},
            cwd=repo,
            env={"AUTO_PILOT_MAIN_OK": "1"},
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── malformed stdin ──

    def test_malformed_stdin_allows(self, hooks_dir, tmp_path):
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="not json",
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=15,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout


class TestDeletionDiffGuard:
    """ⓓ-3 deletion-diff-guard.sh"""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "deletion-diff-guard.sh"

    # ── pass cases ──

    def test_non_push_command_passes(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git commit -m 'test'"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_no_upstream_allows(self, hooks_dir, tmp_path):
        """No git repo / no upstream → allow."""
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git push origin feature"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0

    def test_bypass_env_allows(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git push origin main"}},
            cwd=tmp_path,
            env={"AUTO_PILOT_BIG_DELETE_OK": "1"},
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── malformed stdin ──

    def test_malformed_stdin_allows(self, hooks_dir, tmp_path):
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="not json",
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=15,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout


class TestGhAuthPreflight:
    """ⓓ-4 gh-auth-preflight.sh"""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "gh-auth-preflight.sh"

    def test_non_gh_command_passes(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "git push origin main"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_gh_auth_skipped(self, hooks_dir, tmp_path):
        """gh auth commands are skipped even if user mismatch would fire."""
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "gh auth switch --hostname github.com --user Sewhoan"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_no_remote_allows(self, hooks_dir, tmp_path):
        """No git remote → can't determine expected owner → allow."""
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "gh pr list"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0

    def test_malformed_stdin_allows(self, hooks_dir, tmp_path):
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="not json",
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=15,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_mismatch_fires_deny(self, hooks_dir, tmp_path):
        """Simulate mismatch via cache: active=WrongUser, expected=Sewhoan."""
        import tempfile
        # Set up a git repo with a Sewhoan remote
        subprocess.run(["git", "init", str(tmp_path)], capture_output=True, check=True)
        subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin",
                        "https://github.com/Sewhoan/pickl-api.git"], check=True)

        cache_file = Path(tempfile.gettempdir()) / "gh-auth-Sewhoan.cache"
        cache_file.write_text("WrongUser")
        try:
            r = _run_hook(
                self._hook(hooks_dir),
                {"tool_input": {"command": "gh pr create --title test"}},
                cwd=tmp_path,
            )
            # Either deny (if cache hit) or allow (if gh not available / cache bypassed)
            assert r.returncode == 0
            if r.stdout.strip():
                data = json.loads(r.stdout)
                assert data["hookSpecificOutput"]["permissionDecision"] == "deny"
        finally:
            cache_file.unlink(missing_ok=True)


class TestRuffImportIntegrity:
    """ⓓ-5 ruff-import-integrity.sh (PostToolUse)"""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "ruff-import-integrity.sh"

    def test_non_ruff_command_noop(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "pytest tests/"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_ruff_format_triggers_check(self, hooks_dir, tmp_path):
        """PostToolUse ruff format — hook fires but finds no files (empty repo)."""
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "ruff format src/"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0

    def test_ruff_fix_triggers_check(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command": "ruff check --fix app/"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0

    def test_malformed_stdin_noop(self, hooks_dir, tmp_path):
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="not json",
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=15,
        )
        assert r.returncode == 0


class TestDispatchContractGate:
    """ⓓ-7③ + ⓓ-9 dispatch-contract-gate.sh"""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "dispatch-contract-gate.sh"

    # ── marker absent → allow ──

    def test_no_marker_allows(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {"prompt": "Just run the analysis task."}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_empty_prompt_allows(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {"prompt": ""}},
            cwd=tmp_path,
        )
        assert r.returncode == 0

    # ── marker present, check file missing → deny ──

    def test_marker_present_no_check_file_denies(self, hooks_dir, tmp_path):
        contract_dir = tmp_path / "contracts"
        contract_dir.mkdir()
        (contract_dir / "contract.json").write_text('{"id": "phase-1-alpha", "phase": "1"}')
        # No contract-check.json
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {
                "prompt": f"Worker task. contract_dir={contract_dir} Build the alpha module."
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── marker present, sha mismatch → deny ──

    def test_marker_present_sha_mismatch_denies(self, hooks_dir, tmp_path):
        contract_dir = tmp_path / "contracts"
        contract_dir.mkdir()
        contract_json = contract_dir / "contract.json"
        contract_json.write_text('{"id": "phase-1", "phase": "1"}')
        # Write check file with wrong sha
        (contract_dir / "contract-check.json").write_text(
            '{"contract_sha256": "deadbeefdeadbeef"}'
        )
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {
                "prompt": f"Worker task. contract_dir={contract_dir}"
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── marker present, correct sha, preflight present+fresh → allow ──

    def test_marker_with_valid_sha_and_fresh_preflight_allows(self, hooks_dir, tmp_path):
        contract_dir = tmp_path / "contracts"
        contract_dir.mkdir()
        contract_json = contract_dir / "contract.json"
        contract_json.write_text('{"id": "phase-1", "phase": "1"}')

        # Compute real sha
        sha = subprocess.check_output(
            ["shasum", "-a", "256", str(contract_json)], text=True
        ).split()[0]
        (contract_dir / "contract-check.json").write_text(
            json.dumps({"contract_sha256": sha})
        )

        # Get current HEAD (may fail in a non-git cwd)
        try:
            head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=str(REPO_ROOT), text=True, stderr=subprocess.DEVNULL,
            ).strip()
        except Exception:
            head = "abc123"

        # Write fresh preflight
        preflight_dir = tmp_path / ".planning" / "auto-pilot" / "preflight"
        preflight_dir.mkdir(parents=True)
        # ISO-8601, matching what pm_preflight.sh actually writes (schema
        # format: date-time) — epoch-int fixtures masked a hook parse bug.
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (preflight_dir / "phase-1.json").write_text(
            json.dumps({"generated_ts": now_iso, "head_sha": head})
        )

        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {
                "prompt": f"Worker task. contract_dir={contract_dir}"
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        # With correct sha + fresh preflight: allow (head_sha mismatch only if hook reads
        # different git HEAD than what we wrote — acceptable in isolated tmp_path context)

    # ── TICKET= marker (the REAL dispatch prompt shape) fires the gate ──

    def test_ticket_marker_fires_gate(self, hooks_dir, tmp_path):
        """Live dispatches use `TICKET=<contract_dir>/tickets/<role>.json`
        (pm-orchestrator.md template) — the gate must fire on that shape too
        (review r1: contract_dir=-only matching left the gate inert)."""
        contract_dir = tmp_path / "contracts"
        tickets_dir = contract_dir / "tickets"
        tickets_dir.mkdir(parents=True)
        contract_json = contract_dir / "contract.json"
        contract_json.write_text('{"id": "phase-3", "phase": "3"}')
        ticket = tickets_dir / "worker.json"
        ticket.write_text("{}")
        # NO contract-check.json → gate must deny (proves it fired)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {
                "prompt": f"TICKET={ticket}\nRead ticket. Refuse if ticket_sha mismatch."
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_non_path_ticket_token_allows(self, hooks_dir, tmp_path):
        """Prose `TICKET=PROJ-123` (no slash) is not a worker dispatch — must
        NOT trip the gate (r2 false-deny finding)."""
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {
                "prompt": "Investigate TICKET=PROJ-123 from the issue tracker."
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_ticket_marker_without_contract_json_denies(self, hooks_dir, tmp_path):
        """TICKET= present but no contract.json at the derived dir = PM skipped
        contract prep → deny, not silent allow."""
        tickets_dir = tmp_path / "contracts" / "tickets"
        tickets_dir.mkdir(parents=True)
        ticket = tickets_dir / "worker.json"
        ticket.write_text("{}")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {
                "prompt": f"TICKET={ticket}\nRead ticket."
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── preflight stale → deny ──

    def test_stale_preflight_denies(self, hooks_dir, tmp_path):
        contract_dir = tmp_path / "contracts"
        contract_dir.mkdir()
        contract_json = contract_dir / "contract.json"
        contract_json.write_text('{"id": "phase-2", "phase": "2"}')

        sha = subprocess.check_output(
            ["shasum", "-a", "256", str(contract_json)], text=True
        ).split()[0]
        (contract_dir / "contract-check.json").write_text(
            json.dumps({"contract_sha256": sha})
        )

        # Write stale preflight (> 900s old), ISO-8601 like the real producer
        preflight_dir = tmp_path / ".planning" / "auto-pilot" / "preflight"
        preflight_dir.mkdir(parents=True)
        stale_iso = (datetime.now(timezone.utc) - timedelta(seconds=1000)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        (preflight_dir / "phase-2.json").write_text(
            json.dumps({"generated_ts": stale_iso, "head_sha": "abc123"})
        )

        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {
                "prompt": f"Worker task. contract_dir={contract_dir}"
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── malformed stdin → allow ──

    def test_malformed_stdin_allows(self, hooks_dir, tmp_path):
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="not json",
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=15,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout


class TestCreationGate:
    """ⓓ-10 creation-gate.sh"""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "creation-gate.sh"

    def _fresh_artifact(self, artifact_path: Path, result: str = "clean") -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps({"generated_ts": int(time.time()), "head_sha": "abc", "result": result})
        )

    def _stale_artifact(self, artifact_path: Path) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps({"generated_ts": int(time.time()) - 1000, "head_sha": "abc", "result": "clean"})
        )

    # ── Skill matcher — creator skills ──

    def test_creator_skill_artifact_absent_denies(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Skill", "tool_input": {"skill": "skill-creator:skill-creator"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_creator_skill_artifact_stale_denies(self, hooks_dir, tmp_path):
        self._stale_artifact(tmp_path / ".planning" / "auto-pilot" / "creation-check.json")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Skill", "tool_input": {"skill": "plugin-dev:hook-development"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_creator_skill_artifact_fresh_allows(self, hooks_dir, tmp_path):
        self._fresh_artifact(tmp_path / ".planning" / "auto-pilot" / "creation-check.json")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Skill", "tool_input": {"skill": "plugin-dev:command-development"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_creator_skill_qualified_name_artifact_fresh_allows(self, hooks_dir, tmp_path):
        """Qualified name payload (plugin-dev:create-plugin) with fresh artifact."""
        self._fresh_artifact(tmp_path / ".planning" / "auto-pilot" / "creation-check.json")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Skill", "tool_input": {"skill": "plugin-dev:create-plugin"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── Skill matcher — non-creator skill → allow unconditionally ──

    def test_non_creator_skill_passes_without_artifact(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Skill", "tool_input": {"skill": "auto-pilot:auto-pilot"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_non_creator_skill_vault_build_passes(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Skill", "tool_input": {"skill": "vault-builder:vault-build"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── Task matcher — plugin-dev:agent-creator ──

    def test_task_agent_creator_absent_artifact_denies(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task",
             "tool_input": {"subagent_type": "plugin-dev:agent-creator", "prompt": "create agent"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_task_agent_creator_fresh_artifact_allows(self, hooks_dir, tmp_path):
        self._fresh_artifact(tmp_path / ".planning" / "auto-pilot" / "creation-check.json")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task",
             "tool_input": {"subagent_type": "plugin-dev:agent-creator", "prompt": "create agent"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── Task matcher — non-agent-creator subagent_type → ALLOW (false-deny 방지) ──

    def test_task_non_creator_subagent_passes(self, hooks_dir, tmp_path):
        """Any other subagent_type must NOT be gated — false-deny prevention."""
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task",
             "tool_input": {"subagent_type": "claude-sonnet-4-5", "prompt": "do some work"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    def test_task_subagent_type_codex_passes(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task",
             "tool_input": {"subagent_type": "codex", "prompt": "run analysis"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── Human bypass ──

    def test_human_marker_bypass_allows(self, hooks_dir, tmp_path):
        # No artifact — bypass should allow anyway
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Skill", "tool_input": {"skill": "skill-creator:skill-creator"}},
            cwd=tmp_path,
            env={"AUTO_PILOT_CREATION_OK": "1"},
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

    # ── overlap result → deny ──

    def test_artifact_with_overlap_result_denies(self, hooks_dir, tmp_path):
        self._fresh_artifact(tmp_path / ".planning" / "auto-pilot" / "creation-check.json", result="overlap")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Skill", "tool_input": {"skill": "skill-creator:skill-creator"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    # ── malformed stdin → allow ──

    def test_malformed_stdin_allows(self, hooks_dir, tmp_path):
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="not json",
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=15,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout


class TestHooksJsonWiring:
    """Validate hooks.json has all new entries wired correctly."""

    def _load(self) -> dict:
        hooks_json = Path(__file__).parent.parent / "hooks" / "hooks.json"
        return json.loads(hooks_json.read_text())

    def test_json_valid(self):
        data = self._load()
        assert "hooks" in data

    def test_pre_edit_human_only_wired(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        entry = next(
            (e for e in pre if any("pre-edit-human-only.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "pre-edit-human-only.sh not in hooks.json PreToolUse"
        for tool in ("Edit", "Write", "MultiEdit"):
            assert tool in entry["matcher"], f"{tool} missing from matcher"

    def test_branch_lock_wired_on_bash(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        entry = next(
            (e for e in pre if any("branch-lock.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "branch-lock.sh not in hooks.json"
        assert "Bash" in entry["matcher"]

    def test_deletion_diff_guard_wired_on_bash(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        entry = next(
            (e for e in pre if any("deletion-diff-guard.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "deletion-diff-guard.sh not in hooks.json"
        assert "Bash" in entry["matcher"]

    def test_gh_auth_preflight_wired_on_bash(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        entry = next(
            (e for e in pre if any("gh-auth-preflight.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "gh-auth-preflight.sh not in hooks.json"
        assert "Bash" in entry["matcher"]

    def test_dispatch_contract_gate_wired_on_task(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        entry = next(
            (e for e in pre if any("dispatch-contract-gate.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "dispatch-contract-gate.sh not in hooks.json"
        assert "Task" in entry["matcher"]

    def test_creation_gate_wired_on_skill(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        skill_entry = next(
            (e for e in pre if e["matcher"] == "Skill"
             and any("creation-gate.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert skill_entry is not None, "creation-gate.sh missing Skill entry in hooks.json"

    def test_creation_gate_wired_on_task(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        task_entries = [
            e for e in pre if "Task" in e["matcher"]
            and any("creation-gate.sh" in h["command"] for h in e["hooks"])
        ]
        assert len(task_entries) >= 1, "creation-gate.sh missing Task entry in hooks.json"

    def test_ruff_import_integrity_wired_post_tool_use(self):
        data = self._load()
        post = data["hooks"]["PostToolUse"]
        entry = next(
            (e for e in post if any("ruff-import-integrity.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "ruff-import-integrity.sh not in PostToolUse"
        assert "Bash" in entry["matcher"]

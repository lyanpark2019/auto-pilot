from __future__ import annotations
import os

import json
import subprocess
import time
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

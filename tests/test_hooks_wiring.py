from __future__ import annotations

import json
from pathlib import Path


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

    def test_headless_sync_dispatch_guard_wired(self):
        data = self._load()
        pre = data["hooks"]["PreToolUse"]
        entry = next(
            (e for e in pre if any(
                "headless-sync-dispatch-guard.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "headless-sync-dispatch-guard.sh not wired"
        for tool in ("Task", "Bash"):
            assert tool in entry["matcher"], f"{tool} missing from matcher"


class TestWorkerHHooksJsonWiring:
    """hooks.json wiring for artifact-ledger.sh + context-watch.sh."""

    def _load(self) -> dict:
        hooks_json = Path(__file__).parent.parent / "hooks" / "hooks.json"
        return json.loads(hooks_json.read_text())

    def test_artifact_ledger_wired_post_tool_use_write(self):
        data = self._load()
        post = data["hooks"]["PostToolUse"]
        entry = next(
            (e for e in post if any("artifact-ledger.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "artifact-ledger.sh not in PostToolUse"
        assert entry["matcher"] == "Write"

    def test_context_watch_wired_user_prompt_submit(self):
        data = self._load()
        ups = data["hooks"].get("UserPromptSubmit")
        assert ups, "UserPromptSubmit event missing from hooks.json"
        entry = next(
            (e for e in ups if any("context-watch.sh" in h["command"] for h in e["hooks"])),
            None,
        )
        assert entry is not None, "context-watch.sh not in UserPromptSubmit"
        assert entry["matcher"] == "*"

    def test_both_hooks_use_plugin_root_paths(self):
        data = self._load()
        all_cmds = [
            h["command"]
            for event in data["hooks"].values()
            for e in event
            for h in e["hooks"]
            if "artifact-ledger.sh" in h["command"] or "context-watch.sh" in h["command"]
        ]
        assert len(all_cmds) == 2
        for cmd in all_cmds:
            assert cmd.startswith("${CLAUDE_PLUGIN_ROOT}/hooks/")

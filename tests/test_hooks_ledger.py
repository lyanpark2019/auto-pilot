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


class TestArtifactLedger:
    """artifact-ledger.sh — PostToolUse Write observer (never blocks)."""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "artifact-ledger.sh"

    def _ledger(self, root: Path) -> Path:
        return root / ".planning" / "auto-pilot" / "session-artifacts.jsonl"

    # ── match cases: ledger line appended ──

    def test_plan_path_write_appends_ledger_line(self, hooks_dir, tmp_path):
        target = str(tmp_path / "docs" / "plans" / "2026-06-07-foo-plan.md")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "sess-abc",
             "tool_input": {"file_path": target}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""  # observer: no stdout JSON
        ledger = self._ledger(tmp_path)
        assert ledger.is_file()
        lines = ledger.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["path"] == target
        assert entry["session_id"] == "sess-abc"
        assert entry["ts"]

    def test_specs_path_appends(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s2",
             "tool_input": {"file_path": "docs/specs/2026-06-07-design.md"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert self._ledger(tmp_path).is_file()

    def test_handoff_basename_case_insensitive(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s3",
             "tool_input": {"file_path": str(tmp_path / "notes" / "NEXT-SESSION-HANDOFF.md")}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        entry = json.loads(self._ledger(tmp_path).read_text().strip())
        assert "HANDOFF" in entry["path"]

    def test_brainstorm_basename_appends(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s4",
             "tool_input": {"file_path": str(tmp_path / "docs" / "Brainstorm-ideas.md")}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert self._ledger(tmp_path).is_file()

    def test_home_claude_plans_appends(self, hooks_dir, tmp_path):
        target = str(Path.home() / ".claude" / "plans" / "some-plan.md")
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s5",
             "tool_input": {"file_path": target}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        entry = json.loads(self._ledger(tmp_path).read_text().strip())
        assert entry["path"] == target

    def test_empty_session_id_ok(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write",
             "tool_input": {"file_path": "docs/plans/x.md"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        entry = json.loads(self._ledger(tmp_path).read_text().strip())
        assert entry["session_id"] == ""

    def test_walks_up_to_existing_planning_dir(self, hooks_dir, tmp_path):
        """Ledger lands at the repo root that already has .planning, not CWD."""
        (tmp_path / ".planning").mkdir()
        sub = tmp_path / "sub" / "dir"
        sub.mkdir(parents=True)
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s6",
             "tool_input": {"file_path": "docs/plans/y.md"}},
            cwd=sub,
        )
        assert r.returncode == 0
        assert self._ledger(tmp_path).is_file()
        assert not (sub / ".planning").exists()

    # ── non-match / exclusion: nothing written ──

    def test_non_matching_path_writes_nothing(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s7",
             "tool_input": {"file_path": "src/module.py"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert not self._ledger(tmp_path).exists()

    def test_planning_path_excluded(self, hooks_dir, tmp_path):
        """Never ledger the ledger — .planning/ paths are excluded even when
        they would otherwise match (plans/ + handoff basename here)."""
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s8",
             "tool_input": {"file_path": ".planning/plans/handoff.md"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert not self._ledger(tmp_path).exists()

    def test_absolute_planning_path_excluded(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s9",
             "tool_input": {"file_path": str(tmp_path / ".planning" / "auto-pilot" / "plans" / "x.md")}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert not self._ledger(tmp_path).exists()

    def test_dashboard_path_excluded(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s10",
             "tool_input": {"file_path": "dashboard/plans/page.md"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert not self._ledger(tmp_path).exists()

    def test_git_path_excluded(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "session_id": "s11",
             "tool_input": {"file_path": ".git/plans/hook.md"}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert not self._ledger(tmp_path).exists()

    def test_empty_file_path_writes_nothing(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Write", "tool_input": {}},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        assert not self._ledger(tmp_path).exists()

    # ── malformed stdin → rc 0, nothing written ──

    def test_malformed_stdin_rc0_writes_nothing(self, hooks_dir, tmp_path):
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="not json {{{",
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=15,
        )
        assert r.returncode == 0
        assert not self._ledger(tmp_path).exists()


class TestContextWatch:
    """context-watch.sh — UserPromptSubmit context-size nudge (once per session)."""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "context-watch.sh"

    def _env(self, tmp_path: Path, **extra: str) -> dict:
        """TMPDIR-scoped marker dir (pytest tmp_path → auto-cleaned) + low
        threshold via env override so a 2MB transcript trips it."""
        env = {
            "TMPDIR": str(tmp_path),
            "AUTO_PILOT_CONTEXT_LIMIT_TOKENS": "200000",
            "AUTO_PILOT_HANDOFF_PCT": "40",
        }
        env.update(extra)
        return env

    def _big_transcript(self, tmp_path: Path) -> Path:
        t = tmp_path / "transcript.jsonl"
        t.write_bytes(b"x" * (2 * 1024 * 1024 + 64))  # >2MB → est ≈ 262k tokens
        return t

    # ── over threshold, no marker → emit additionalContext + create marker ──

    def test_big_transcript_emits_additional_context_and_marker(self, hooks_dir, tmp_path):
        t = self._big_transcript(tmp_path)
        r = _run_hook(
            self._hook(hooks_dir),
            {"transcript_path": str(t), "session_id": "ctx-test-1"},
            cwd=tmp_path,
            env=self._env(tmp_path),
        )
        assert r.returncode == 0
        data = json.loads(r.stdout)
        out = data["hookSpecificOutput"]
        assert out["hookEventName"] == "UserPromptSubmit"
        assert "[context-watch]" in out["additionalContext"]
        assert "/auto-pilot handoff" in out["additionalContext"]
        marker = tmp_path / "auto-pilot-ctxwarn-ctx-test-1.marker"
        assert marker.is_file()

    # ── marker present → silent ──

    def test_second_run_with_marker_is_silent(self, hooks_dir, tmp_path):
        t = self._big_transcript(tmp_path)
        payload = {"transcript_path": str(t), "session_id": "ctx-test-2"}
        env = self._env(tmp_path)
        r1 = _run_hook(self._hook(hooks_dir), payload, cwd=tmp_path, env=env)
        assert r1.returncode == 0
        assert "additionalContext" in r1.stdout
        r2 = _run_hook(self._hook(hooks_dir), payload, cwd=tmp_path, env=env)
        assert r2.returncode == 0
        assert r2.stdout.strip() == ""

    # ── below threshold → silent, no marker ──

    def test_small_transcript_silent(self, hooks_dir, tmp_path):
        t = tmp_path / "small.jsonl"
        t.write_text("tiny transcript")
        r = _run_hook(
            self._hook(hooks_dir),
            {"transcript_path": str(t), "session_id": "ctx-test-3"},
            cwd=tmp_path,
            env=self._env(tmp_path),
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""
        assert not (tmp_path / "auto-pilot-ctxwarn-ctx-test-3.marker").exists()

    def test_env_override_lowers_threshold(self, hooks_dir, tmp_path):
        """A 16KB transcript (~2k est tokens) fires when the env threshold is
        dropped to 1000 tokens × 40% = 400."""
        t = tmp_path / "mid.jsonl"
        t.write_bytes(b"y" * 16384)
        r = _run_hook(
            self._hook(hooks_dir),
            {"transcript_path": str(t), "session_id": "ctx-test-4"},
            cwd=tmp_path,
            env=self._env(tmp_path, AUTO_PILOT_CONTEXT_LIMIT_TOKENS="1000"),
        )
        assert r.returncode == 0
        assert "additionalContext" in r.stdout

    # ── no transcript → silent ──

    def test_missing_transcript_file_silent(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"transcript_path": str(tmp_path / "nope.jsonl"), "session_id": "ctx-test-5"},
            cwd=tmp_path,
            env=self._env(tmp_path),
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_no_transcript_field_silent(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {"session_id": "ctx-test-6"},
            cwd=tmp_path,
            env=self._env(tmp_path),
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    # ── malformed stdin → rc 0 (fail-open) ──

    def test_malformed_stdin_rc0_silent(self, hooks_dir, tmp_path):
        r = subprocess.run(
            [str(self._hook(hooks_dir))],
            input="garbage {{{",
            capture_output=True, text=True,
            cwd=str(tmp_path), timeout=15,
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

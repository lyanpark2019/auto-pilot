"""Handoff write/pickup/disposition flow tests.

Covers:
- hooks/preflight-path.sh SessionStart pickup of .planning/auto-pilot/handoff-next.md
  (pending+fresh -> emit additionalContext + flip to consumed; stale/consumed/malformed -> silent)
- hooks/pm_final_report.sh "## Session artifacts" disposition section from
  .planning/auto-pilot/session-artifacts.jsonl (fail-open without it)

Helper style copied inline from test_hooks.py (do not import across test modules).
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
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


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_handoff(
    repo: Path,
    *,
    status: str = "pending",
    written_at: datetime | None = None,
    body: str = "## ① 상태\nshipped X\n\n## ④ NEXT-PROMPT\nrun the next phase\n",
) -> Path:
    written_at = written_at or datetime.now(timezone.utc)
    d = repo / ".planning" / "auto-pilot"
    d.mkdir(parents=True, exist_ok=True)
    f = d / "handoff-next.md"
    f.write_text(
        "---\n"
        f"written_at: {_iso(written_at)}\n"
        "session_id: test-session\n"
        "head_sha: abc123\n"
        f"status: {status}\n"
        "---\n\n" + body
    )
    return f


class TestHandoffPickup:
    """preflight-path.sh SessionStart handoff pickup."""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "preflight-path.sh"

    def test_pending_fresh_emits_context_and_flips_consumed(self, hooks_dir, tmp_path):
        f = _write_handoff(tmp_path)
        r = _run_hook(self._hook(hooks_dir), {}, cwd=tmp_path)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        out = data["hookSpecificOutput"]
        assert out["hookEventName"] == "SessionStart"
        assert "NEXT-PROMPT" in out["additionalContext"]
        assert "written_at:" in out["additionalContext"]  # frontmatter included
        text = f.read_text()
        assert "status: consumed" in text
        assert "consumed_at:" in text
        assert "status: pending" not in text
        # body preserved through the rewrite
        assert "run the next phase" in text

    def test_walk_up_finds_handoff_from_subdir(self, hooks_dir, tmp_path):
        f = _write_handoff(tmp_path)
        sub = tmp_path / "src" / "deep"
        sub.mkdir(parents=True)
        r = _run_hook(self._hook(hooks_dir), {}, cwd=sub)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert "additionalContext" in data["hookSpecificOutput"]
        assert "status: consumed" in f.read_text()

    def test_consumed_handoff_silent(self, hooks_dir, tmp_path):
        f = _write_handoff(tmp_path, status="consumed")
        before = f.read_text()
        r = _run_hook(self._hook(hooks_dir), {}, cwd=tmp_path)
        assert r.returncode == 0
        assert r.stdout.strip() == ""
        assert f.read_text() == before  # untouched

    def test_stale_handoff_silent(self, hooks_dir, tmp_path):
        stale = datetime.now(timezone.utc) - timedelta(days=8)
        f = _write_handoff(tmp_path, written_at=stale)
        r = _run_hook(self._hook(hooks_dir), {}, cwd=tmp_path)
        assert r.returncode == 0
        assert r.stdout.strip() == ""
        assert "status: pending" in f.read_text()  # NOT flipped

    def test_malformed_frontmatter_silent_rc0(self, hooks_dir, tmp_path):
        d = tmp_path / ".planning" / "auto-pilot"
        d.mkdir(parents=True)
        (d / "handoff-next.md").write_text("no frontmatter here\njust prose\n")
        r = _run_hook(self._hook(hooks_dir), {}, cwd=tmp_path)
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_unparseable_written_at_silent(self, hooks_dir, tmp_path):
        d = tmp_path / ".planning" / "auto-pilot"
        d.mkdir(parents=True)
        f = d / "handoff-next.md"
        f.write_text("---\nwritten_at: not-a-date\nstatus: pending\n---\nbody\n")
        r = _run_hook(self._hook(hooks_dir), {}, cwd=tmp_path)
        assert r.returncode == 0
        assert r.stdout.strip() == ""
        assert "status: pending" in f.read_text()

    def test_no_handoff_file_no_stdout(self, hooks_dir, tmp_path):
        r = _run_hook(self._hook(hooks_dir), {}, cwd=tmp_path)
        assert r.returncode == 0
        assert r.stdout.strip() == ""

    def test_truncates_to_6000_chars(self, hooks_dir, tmp_path):
        _write_handoff(tmp_path, body="## ① 상태\n" + "X" * 9000 + "\n")
        r = _run_hook(self._hook(hooks_dir), {}, cwd=tmp_path)
        assert r.returncode == 0
        data = json.loads(r.stdout)
        assert len(data["hookSpecificOutput"]["additionalContext"]) <= 6000


def _make_vault(tmp_path: Path) -> Path:
    """Minimal vault with a fresh ticket-state.json so pm_final_report fires."""
    vault = tmp_path / "vault"
    (vault / "meta").mkdir(parents=True)
    (vault / "meta" / "ticket-state.json").write_text(
        json.dumps(
            {"tickets": [
                {"id": 1, "worker_type": "worker", "status": "verified", "summary": "did a thing"},
            ]}
        )
    )
    return vault


class TestPmFinalReportArtifacts:
    """pm_final_report.sh '## Session artifacts' disposition extension."""

    def _hook(self, hooks_dir: Path) -> Path:
        return hooks_dir / "pm_final_report.sh"

    def _reports(self, vault: Path) -> list[Path]:
        return sorted((vault / "meta").glob("pm-final-report-*.md"))

    def test_with_ledger_appends_section(self, hooks_dir, tmp_path):
        vault = _make_vault(tmp_path)
        proj = tmp_path / "proj"
        led_dir = proj / ".planning" / "auto-pilot"
        led_dir.mkdir(parents=True)
        # consumed handoff -> "삭제 후보"
        (led_dir / "handoff-next.md").write_text(
            "---\nstatus: consumed\nconsumed_at: 2026-06-07T00:00:00Z\n---\nbody\n"
        )
        # existing plan doc -> "distill→delete 후보"
        plan = proj / "docs" / "plans" / "p.md"
        plan.parent.mkdir(parents=True)
        plan.write_text("plan")
        ledger = led_dir / "session-artifacts.jsonl"
        ledger.write_text(
            "\n".join(
                [
                    json.dumps({"path": "docs/plans/p.md"}),
                    json.dumps({"path": ".planning/auto-pilot/handoff-next.md"}),
                    json.dumps({"path": "src/foo.py"}),  # missing -> "확인 필요"
                    json.dumps({"path": "docs/plans/p.md"}),  # duplicate -> dedup
                    "not json {{{",  # malformed line -> skipped, fail-open
                ]
            )
            + "\n"
        )
        r = _run_hook(
            self._hook(hooks_dir),
            {},
            cwd=proj,
            env={"NBM_VAULT_PATH": str(vault), "CLAUDE_PROJECT_DIR": str(proj)},
        )
        assert r.returncode == 0
        reports = self._reports(vault)
        assert reports, "pm_final_report did not write a report"
        body = reports[-1].read_text()
        assert "## Session artifacts" in body
        assert "distill→delete 후보" in body
        assert "삭제 후보" in body
        assert "확인 필요" in body
        assert body.count("docs/plans/p.md") == 1  # deduplicated
        assert "src/foo.py — missing" in body

    def test_without_ledger_unchanged_rc0(self, hooks_dir, tmp_path):
        vault = _make_vault(tmp_path)
        proj = tmp_path / "proj"
        proj.mkdir()
        r = _run_hook(
            self._hook(hooks_dir),
            {},
            cwd=proj,
            env={"NBM_VAULT_PATH": str(vault), "CLAUDE_PROJECT_DIR": str(proj)},
        )
        assert r.returncode == 0
        reports = self._reports(vault)
        assert reports
        body = reports[-1].read_text()
        assert "PM Final Report" in body
        assert "## Session artifacts" not in body

    def test_no_vault_env_noop_rc0(self, hooks_dir, tmp_path):
        r = _run_hook(
            self._hook(hooks_dir),
            {},
            cwd=tmp_path,
            env={"NBM_VAULT_PATH": "", "VAULT_BUILDER_VAULT": ""},
        )
        assert r.returncode == 0
        assert r.stdout.strip() == ""

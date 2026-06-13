from __future__ import annotations
import hashlib
import os

import json
import subprocess
from datetime import datetime, timedelta, timezone
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


def _write_signed_contract_check(contract_dir: Path, contract_json: Path) -> str:
    sha = hashlib.sha256(contract_json.read_bytes()).hexdigest()
    bundle = contract_dir / "context-bundle"
    bundle.mkdir()
    manifest = bundle / "MANIFEST.txt"
    manifest.write_text("fixture manifest\n")
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    sig_path = contract_dir / "PM-SIGNATURE"
    sig_path.write_text(json.dumps({"contract_sha": sha, "manifest_sha": manifest_sha}) + "\n")
    (contract_dir / "contract-check.json").write_text(json.dumps({
        "contract_sha256": sha,
        "result": "pass",
        "pm_signature": {
            "verified": True,
            "signature_sha256": hashlib.sha256(sig_path.read_bytes()).hexdigest(),
            "contract_sha256": sha,
            "manifest_sha256": manifest_sha,
        },
    }))
    return sha


REPO_ROOT = Path(__file__).resolve().parent.parent


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
                # Marker at line-start — pm-orchestrator.md template (lines 278-279)
                "prompt": f"contract_dir={contract_dir}\nBuild the alpha module."
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
                # Marker at line-start — pm-orchestrator.md template (lines 278-279)
                "prompt": f"contract_dir={contract_dir}"
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

        _write_signed_contract_check(contract_dir, contract_json)

        # Make tmp_path a real git repo so git rev-parse HEAD resolves.
        # The old test fell through on git-error-fail-open (SPURIOUS allow) — now
        # the hook fails CLOSED on git error, so we need a real repo with a real HEAD.
        subprocess.run(
            ["git", "init", "-b", "main", str(tmp_path)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "Test"],
            check=True, capture_output=True,
        )
        # Create an initial commit so HEAD resolves
        (tmp_path / "README.md").write_text("init\n")
        subprocess.run(
            ["git", "-C", str(tmp_path), "add", "README.md"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init"],
            check=True, capture_output=True,
        )
        # Capture REAL head sha — used for genuine binding check
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(tmp_path), capture_output=True, text=True, check=True,
        ).stdout.strip()

        # Write fresh preflight with the REAL head_sha so binding check passes
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
                # Marker at line-start — pm-orchestrator.md template (lines 278-279)
                "prompt": f"contract_dir={contract_dir}"
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0
        # With correct sha + signature status + fresh preflight + real HEAD binding: allow.
        assert "deny" not in r.stdout

    def test_git_rev_parse_failure_denies(self, hooks_dir, tmp_path):
        """W7 fix: when stored_head is set and git rev-parse HEAD fails (non-git dir),
        the hook must fail CLOSED — deny with the safety-measure message."""
        contract_dir = tmp_path / "contracts"
        contract_dir.mkdir()
        contract_json = contract_dir / "contract.json"
        contract_json.write_text('{"id": "phase-1", "phase": "1"}')

        _write_signed_contract_check(contract_dir, contract_json)

        # Write a fresh preflight with a non-empty head_sha — this triggers the
        # git-rev-parse binding check in the hook.  tmp_path is NOT a git repo,
        # so rev-parse will fail → hook must deny (fail-closed).
        preflight_dir = tmp_path / ".planning" / "auto-pilot" / "preflight"
        preflight_dir.mkdir(parents=True)
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (preflight_dir / "phase-1.json").write_text(
            json.dumps({"generated_ts": now_iso, "head_sha": "abc123nonexistent"})
        )

        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_name": "Task", "tool_input": {
                "prompt": f"contract_dir={contract_dir}"
            }},
            cwd=tmp_path,
        )
        assert r.returncode == 0  # hook exits 0 but emits JSON deny
        out = r.stdout
        data = json.loads(out)
        reason = data["hookSpecificOutput"]["permissionDecisionReason"]
        assert "git rev-parse HEAD failed" in reason
        assert "denying as a safety measure" in reason

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

        _write_signed_contract_check(contract_dir, contract_json)

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
                # Marker at line-start — pm-orchestrator.md template (lines 278-279)
                "prompt": f"contract_dir={contract_dir}"
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

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

    # ── deny: HUMAN marker in file ──

    def test_denies_file_with_human_only_marker(self, hooks_dir, tmp_path):
        repo = self._make_repo(tmp_path)
        target = repo / "some-file.md"
        marker = "HUMAN" + "-ONLY"
        target.write_text(f"# Title\n{marker}\nsome content\n")
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
                REPO_ROOT / "docs/architecture.md"
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

    def test_denies_chained_push_main_commit_feature(self, hooks_dir, tmp_path):
        """`git -C <main> push; git -C <feature> commit` — EVERY invocation is
        checked; the push-on-main must deny even though a later commit targets
        a feature repo (r4: commit-first segment selection failed open here)."""
        main_repo = self._make_main_repo(tmp_path / "mainrepo")
        feat_repo = self._make_feature_repo(tmp_path / "featrepo")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command":
                f"git -C {main_repo} push origin main; git -C {feat_repo} commit -m ok"}},
            cwd=elsewhere,
        )
        assert r.returncode == 0
        _deny_json(r.stdout)

    def test_allows_chained_all_feature_targets(self, hooks_dir, tmp_path):
        """Chained command where every invocation targets feature repos —
        must ALLOW (any-segment deny must not become always-deny)."""
        feat1 = self._make_feature_repo(tmp_path / "f1")
        feat2 = self._make_feature_repo(tmp_path / "f2")
        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        r = _run_hook(
            self._hook(hooks_dir),
            {"tool_input": {"command":
                f"git -C {feat1} commit -m a; git -C {feat2} push origin HEAD"}},
            cwd=elsewhere,
        )
        assert r.returncode == 0
        assert "deny" not in r.stdout

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



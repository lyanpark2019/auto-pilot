"""Tests for scripts/docs/check_doc_reference_integrity.py."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).parent.parent
    / "scripts" / "docs" / "check_doc_reference_integrity.py"
)


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), "--root", str(root)],
        capture_output=True, text=True, timeout=30,
    )


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """Minimal repo structure with one Python file under scripts/."""
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / "helper.py"
    target.write_text("def foo():\n    pass\n")
    docs = tmp_path / "docs"
    docs.mkdir()
    return tmp_path


def _write_minimal_assets(repo: Path) -> None:
    skill = repo / "skills" / "alpha"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: alpha\n---\n")
    agents = repo / "agents"
    agents.mkdir()
    (agents / "worker.md").write_text("# worker\n")
    commands = repo / "commands"
    commands.mkdir()
    (commands / "run.md").write_text("# run\n")
    hooks = repo / "hooks"
    hooks.mkdir()
    (hooks / "guard.sh").write_text("#!/usr/bin/env bash\n")
    codex_skill = repo / "codex" / "skills" / "audit"
    codex_skill.mkdir(parents=True)


class TestValidCitations:
    def test_no_citations_exits_clean(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text("No citations here.\n")
        r = _run(repo)
        assert r.returncode == 0
        assert "0 violations" in r.stdout

    def test_valid_file_and_line_exits_clean(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "See `scripts/helper.py:1` for the definition.\n"
        )
        r = _run(repo)
        assert r.returncode == 0

    def test_valid_range_citation_exits_clean(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "Covered in `scripts/helper.py:1-2` (both lines).\n"
        )
        r = _run(repo)
        assert r.returncode == 0


class TestViolations:
    def test_missing_file_is_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "See `scripts/gone.py:1` which is deleted.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "scripts/gone.py:1" in r.stdout
        assert "file not found" in r.stdout

    def test_line_beyond_eof_is_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "See `scripts/helper.py:999` for the definition.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "scripts/helper.py:999" in r.stdout
        assert "999 >" in r.stdout

    def test_range_end_beyond_eof_is_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "Range `scripts/helper.py:1-999` is too wide.\n"
        )
        r = _run(repo)
        assert r.returncode == 1

    def test_bare_filename_without_directory_is_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "See `helper.py:1` — bare name, no directory prefix.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "helper.py:1" in r.stdout

    def test_suggestion_shows_file_length(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "`scripts/helper.py:999` is past EOF.\n"
        )
        r = _run(repo)
        assert "has 2 lines" in r.stdout


class TestIgnoreMarker:
    def test_cite_ignore_suppresses_violation(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "Historical: `scripts/gone.py:1` <!-- cite-ignore -->\n"
        )
        r = _run(repo)
        assert r.returncode == 0
        assert "0 violations" in r.stdout


class TestAssetCountClaims:
    def test_live_asset_count_mismatch_is_violation(self, repo: Path) -> None:
        _write_minimal_assets(repo)
        (repo / "docs" / "guide.md").write_text(
            "Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): "
            "2 skills · 1 agents · 1 commands · 1 hooks · 1 codex-skills = "
            "6 assets total.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "asset count mismatch" in r.stdout
        assert "skills: said 2, actual 1" in r.stdout
        assert "assets: said 6, actual 5" in r.stdout

    def test_source_comment_collect_assets_count_mismatch_is_violation(self, repo: Path) -> None:
        (repo / "scripts" / "registry.py").write_text(
            "# registry at 80 vs build_dashboard_data.collect_assets' canonical 77\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "scripts/registry.py:1" in r.stdout
        assert "asset count mismatch" in r.stdout

    def test_historical_asset_count_snapshot_is_allowed(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "Historical Round-1 snapshot (113 assets, recorded before consolidation).\n"
        )
        r = _run(repo)
        assert r.returncode == 0

    def test_asset_total_includes_skill_shells(self, repo: Path) -> None:
        (repo / "skills" / "retired-shell").mkdir(parents=True)
        (repo / "docs" / "guide.md").write_text(
            "Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): "
            "0 skills · 0 agents · 0 commands · 0 hooks · 0 codex-skills = "
            "1 assets total.\n"
        )
        r = _run(repo)
        assert r.returncode == 0

    def test_asset_counts_use_build_dashboard_data_collect_assets(self, repo: Path) -> None:
        (repo / "scripts" / "build_dashboard_data.py").write_text(
            "def collect_assets():\n"
            "    return [\n"
            "        {'type': 'skill', 'name': 'alpha'},\n"
            "        {'type': 'hook', 'name': 'one.sh'},\n"
            "        {'type': 'hook', 'name': 'two.py'},\n"
            "    ]\n"
        )
        (repo / "docs" / "guide.md").write_text(
            "Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): "
            "1 skills · 0 agents · 0 commands · 2 hooks · 0 codex-skills = "
            "3 assets total.\n"
        )
        r = _run(repo)
        assert r.returncode == 0


def _write_hooks_json(repo: Path, names: list[str]) -> None:
    """Write a hooks/hooks.json wiring the given hook script names."""
    hooks = repo / "hooks"
    hooks.mkdir(exist_ok=True)
    entries = ", ".join(
        f'{{"hooks": [{{"command": "${{CLAUDE_PLUGIN_ROOT}}/hooks/{n}"}}]}}'
        for n in names
    )
    (hooks / "hooks.json").write_text(f'{{"PreToolUse": [{entries}]}}\n')


class TestHookCountClaims:
    """Free-text '(N scripts)' / 'N hooks' claims tied to hooks.json must match."""

    def test_correct_hook_count_in_claude_md_is_ok(self, repo: Path) -> None:
        _write_hooks_json(repo, ["a.sh", "b.sh", "c.py"])
        (repo / "CLAUDE.md").write_text(
            "wiring SoT = `hooks/hooks.json` (3 scripts)\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout
        assert "0 violations" in r.stdout

    def test_correct_hook_count_in_architecture_is_ok(self, repo: Path) -> None:
        _write_hooks_json(repo, ["a.sh", "b.py"])
        (repo / "docs" / "architecture.md").write_text(
            "hooks/  (2 scripts, P; hooks/hooks.json is wiring SoT)\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout

    def test_wrong_scripts_count_is_violation(self, repo: Path) -> None:
        _write_hooks_json(repo, ["a.sh", "b.sh", "c.py"])
        (repo / "docs" / "architecture.md").write_text(
            "hooks/  (21 scripts, P; hooks/hooks.json is wiring SoT)\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "hook-count mismatch" in r.stdout
        assert "said 21" in r.stdout
        assert "actual 3" in r.stdout

    def test_wrong_hooks_count_is_violation(self, repo: Path) -> None:
        _write_hooks_json(repo, ["a.sh", "b.sh"])
        (repo / "CLAUDE.md").write_text(
            "full wiring SoT = `hooks/hooks.json` (9 hooks)\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "hook-count mismatch" in r.stdout
        assert "actual 2" in r.stdout

    def test_count_without_hooks_json_context_is_ignored(self, repo: Path) -> None:
        """A '(N scripts)' line that does NOT name hooks.json never fires."""
        _write_hooks_json(repo, ["a.sh"])
        (repo / "docs" / "architecture.md").write_text(
            "The PR1-PR5 modules (99 scripts) live under scripts/.\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout

    def test_asset_count_line_not_double_counted_as_hooks(self, repo: Path) -> None:
        """The live-asset-count line (collect_assets) is exempt from the hook guard."""
        _write_minimal_assets(repo)
        _write_hooks_json(repo, ["a.sh"])
        # asset line claims 1 hooks (matches _write_minimal_assets' single hook),
        # but hooks.json wires only a.sh — the hook guard must NOT fire here.
        (repo / "docs" / "architecture.md").write_text(
            "Live asset counts (from `scripts/build_dashboard_data.collect_assets()`): "
            "1 skills · 1 agents · 1 commands · 1 hooks · 1 codex-skills = "
            "5 assets total. See `hooks/hooks.json`.\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout

    def test_historical_hook_count_is_allowed(self, repo: Path) -> None:
        _write_hooks_json(repo, ["a.sh"])
        (repo / "docs" / "architecture.md").write_text(
            "Legacy round-1 wiring: hooks/hooks.json once had (21 scripts).\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout


class TestScanScope:
    def test_claude_md_at_root_is_scanned(self, repo: Path) -> None:
        (repo / "CLAUDE.md").write_text(
            "See `scripts/gone.py:1` for context.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "CLAUDE.md" in r.stdout

    def test_dot_claude_docs_scanned(self, repo: Path) -> None:
        dot_claude = repo / ".claude"
        dot_claude.mkdir()
        (dot_claude / "notes.md").write_text(
            "`scripts/gone.py:1` — stale.\n"
        )
        r = _run(repo)
        assert r.returncode == 1

    def test_worktrees_are_excluded(self, repo: Path) -> None:
        wt = repo / ".claude" / "worktrees" / "agent-abc"
        wt.mkdir(parents=True)
        (wt / "stale.md").write_text(
            "`scripts/gone.py:1` — inside worktree, should be skipped.\n"
        )
        r = _run(repo)
        assert r.returncode == 0

    def test_multiple_violations_all_listed(self, repo: Path) -> None:
        (repo / "docs" / "guide.md").write_text(
            "`scripts/gone.py:1`\n`scripts/also-gone.py:2`\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "2 violation" in r.stdout


class TestSymbolWarn:
    """Pin the symbol-proximity behaviour for canonical docs and docs/specs/.

    For canonical docs (outside docs/specs/), a nearby symbol absent from the
    cited line window is a hard VIOLATION (exit 1).
    For docs/specs/**, it stays a WARN on stderr (exit 0) — specs are historical
    planning docs, distilled+deleted per CLAUDE.md, so stale proximity is expected.
    """

    def _make_code_file(self, repo: Path, fn_line: int) -> None:
        """Write scripts/code.py with `def foo():` at `fn_line` (1-based)."""
        padding = ["# padding\n"] * (fn_line - 1)
        (repo / "scripts" / "code.py").write_text(
            "".join(padding) + "def foo():\n    pass\n"
        )

    def test_symbol_at_wrong_line_is_violation_in_canonical_doc(self, repo: Path) -> None:
        """Citation pointing to line 5 when `foo` is at line 50 → VIOLATION in canonical doc."""
        self._make_code_file(repo, fn_line=50)
        (repo / "docs" / "guide.md").write_text(
            "`foo` lives in `scripts/code.py:5`\n"
        )
        r = _run(repo)
        assert r.returncode == 1, "missing symbol in canonical doc must be a violation"
        assert "foo" in r.stdout
        assert "not found near" in r.stdout

    def test_no_warn_for_symbol_at_correct_line(self, repo: Path) -> None:
        """`foo` cited at the line it actually lives on → no WARN."""
        self._make_code_file(repo, fn_line=3)
        # cite line 3 where foo actually is
        (repo / "docs" / "guide.md").write_text(
            "`foo` is defined at `scripts/code.py:3`\n"
        )
        r = _run(repo)
        assert r.returncode == 0
        assert "WARN" not in r.stderr


class TestSpecsCarveOut:
    """docs/specs/** paths get WARN-only treatment for symbol proximity."""

    def _make_code_file(self, repo: Path, fn_line: int) -> None:
        padding = ["# padding\n"] * (fn_line - 1)
        (repo / "scripts" / "code.py").write_text(
            "".join(padding) + "def foo():\n    pass\n"
        )

    def test_missing_symbol_in_specs_is_warn_only(self, repo: Path) -> None:
        """Missing symbol in docs/specs/** stays WARN (exit 0), not a violation."""
        self._make_code_file(repo, fn_line=50)
        specs = repo / "docs" / "specs"
        specs.mkdir(parents=True, exist_ok=True)
        (specs / "plan.md").write_text(
            "`foo` lives in `scripts/code.py:5`\n"
        )
        r = _run(repo)
        assert r.returncode == 0, "specs doc symbol mismatch must stay WARN-only (exit 0)"
        assert "WARN" in r.stderr
        assert "foo" in r.stderr

    def test_missing_symbol_in_canonical_doc_fails(self, repo: Path) -> None:
        """Missing symbol in canonical doc (not docs/specs/) is a hard VIOLATION."""
        self._make_code_file(repo, fn_line=50)
        (repo / "docs" / "guide.md").write_text(
            "`foo` lives in `scripts/code.py:5`\n"
        )
        r = _run(repo)
        assert r.returncode == 1, "canonical doc symbol mismatch must be exit 1"
        assert "not found near" in r.stdout


class TestAnchorCitations:
    """path#token anchor form — line-shift-immune symbol citations."""

    def test_valid_anchor_identifier_exits_clean(self, repo: Path) -> None:
        """Doc cites pkg/mod.py#my_func where def my_func exists → 0 violations."""
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def my_func():\n    pass\n")
        (repo / "docs" / "guide.md").write_text(
            "See `pkg/mod.py#my_func` for the implementation.\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout
        assert "0 violations" in r.stdout

    def test_missing_symbol_is_violation(self, repo: Path) -> None:
        """Doc cites pkg/mod.py#ghost_sym not in file → 1 violation mentioning the token."""
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def my_func():\n    pass\n")
        (repo / "docs" / "guide.md").write_text(
            "See `pkg/mod.py#ghost_sym` — symbol does not exist.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "ghost_sym" in r.stdout
        assert "anchor symbol" in r.stdout

    def test_missing_file_is_violation(self, repo: Path) -> None:
        """Doc cites pkg/nope.py#x where the file does not exist → 1 violation."""
        (repo / "docs" / "guide.md").write_text(
            "See `pkg/nope.py#x` — file is missing.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "file not found" in r.stdout

    def test_filename_token_present_exits_clean(self, repo: Path) -> None:
        """Doc cites hooks/hooks.json#branch-lock.sh where that string is in the json → 0 violations."""
        hooks = repo / "hooks"
        hooks.mkdir()
        (hooks / "hooks.json").write_text(
            '{"PreToolUse": [{"command": "hooks/branch-lock.sh"}]}\n'
        )
        (repo / "docs" / "guide.md").write_text(
            "Wired in `hooks/hooks.json#branch-lock.sh`.\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout

    def test_filename_token_absent_is_violation(self, repo: Path) -> None:
        """Doc cites hooks/hooks.json#missing.sh where that string is NOT in the json → 1 violation."""
        hooks = repo / "hooks"
        hooks.mkdir()
        (hooks / "hooks.json").write_text(
            '{"PreToolUse": [{"command": "hooks/branch-lock.sh"}]}\n'
        )
        (repo / "docs" / "guide.md").write_text(
            "Wired in `hooks/hooks.json#missing.sh`.\n"
        )
        r = _run(repo)
        assert r.returncode == 1
        assert "missing.sh" in r.stdout
        assert "anchor symbol" in r.stdout

    def test_heading_slug_file_exists_exits_clean(self, repo: Path) -> None:
        """Slug whose normalized form is present in target (spaced heading) → 0 violations.

        'some-heading' normalizes to 'someheading'; '## Some Heading' also
        normalizes to 'someheading' — the substring check passes.
        """
        (repo / "docs" / "guide.md").write_text(
            "## Some Heading\n\nBody text.\n"
        )
        (repo / "docs" / "other.md").write_text(
            "See [guide](docs/guide.md#some-heading) for details.\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout

    def test_dash_token_absent_normalized_is_violation(self, repo: Path) -> None:
        """Dash-slug token whose normalized form is NOT in target → exactly 1 violation.

        Closes the P2 blind spot: #totally-bogus-anchor against a file that
        has no text containing 'totallybogusanchor' must be caught.
        """
        (repo / "docs" / "guide.md").write_text(
            "## Real Heading\n\nSome body text.\n"
        )
        (repo / "docs" / "other.md").write_text(
            "See `docs/guide.md#totally-bogus-anchor` for details.\n"
        )
        r = _run(repo)
        assert r.returncode == 1, r.stdout
        assert "totally-bogus-anchor" in r.stdout
        assert "anchor symbol" in r.stdout

    def test_dash_token_present_as_spaced_heading_exits_clean(self, repo: Path) -> None:
        """Slug token whose normalized form IS present (via spaced heading text) → 0 violations.

        File has '## Some Heading', doc cites 'f.md#Some-Heading'.
        normalize('Some-Heading') == normalize('## Some Heading') == 'someheading'.
        """
        (repo / "docs" / "ref.md").write_text(
            "## Some Heading\n\nBody.\n"
        )
        (repo / "docs" / "other.md").write_text(
            "See `docs/ref.md#Some-Heading` for an example.\n"
        )
        r = _run(repo)
        assert r.returncode == 0, r.stdout

    def test_cite_ignore_suppresses_anchor_violation(self, repo: Path) -> None:
        """A line with cite-ignore and a broken anchor → 0 violations."""
        pkg = repo / "pkg"
        pkg.mkdir()
        (pkg / "mod.py").write_text("def my_func():\n    pass\n")
        (repo / "docs" / "guide.md").write_text(
            "Historical: `pkg/mod.py#gone_sym` <!-- cite-ignore -->\n"
        )
        r = _run(repo)
        assert r.returncode == 0
        assert "0 violations" in r.stdout

    def test_existing_path_line_citation_unaffected(self, repo: Path) -> None:
        """Regression: existing path:line citations still work after anchor support added."""
        (repo / "docs" / "guide.md").write_text(
            "See `scripts/helper.py:1` for the definition.\n"
        )
        r = _run(repo)
        assert r.returncode == 0

"""Tests for scripts/build_dashboard_data.py.

Strategy: the module computes ROOT/OUT/ARCH_HTML_OUT/SCORE_DIR at import time and
collect_assets()/load_rounds()/main() read those module globals. To exercise the
code against a throwaway tree WITHOUT ever writing the real repo `dashboard/`, we
monkeypatch those globals to point at a tmp_path-built fake plugin tree. We import
the functions and never invoke the script as a repo-mutating subprocess.

conftest.py already puts scripts/ on sys.path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import build_dashboard_data as m


# --------------------------------------------------------------------------- #
# Fake plugin tree fixtures
# --------------------------------------------------------------------------- #
def _make_tree(root: Path) -> None:
    """Create a minimal plugin tree exercising every collect_assets() branch."""
    # skills/: one real SKILL.md dir, one deprecated shell (no SKILL.md)
    (root / "skills" / "doc-management").mkdir(parents=True)
    (root / "skills" / "doc-management" / "SKILL.md").write_text("# doc\n")
    (root / "skills" / "auto-pilot").mkdir(parents=True)
    (root / "skills" / "auto-pilot" / "SKILL.md").write_text("# loop\n")
    (root / "skills" / "deprecated-shell").mkdir(parents=True)  # no SKILL.md -> skill-shell
    # a stray file directly under skills/ must be ignored (not a dir)
    (root / "skills" / "stray.txt").write_text("ignore me\n")

    # agents/: includes the reviewer quirk fixtures
    (root / "agents").mkdir(parents=True)
    for name in ("pm-orchestrator", "auto-pilot-codex-reviewer", "tech-critic"):
        (root / "agents" / f"{name}.md").write_text(f"# {name}\n")
    (root / "agents" / "not-md.txt").write_text("ignored\n")  # non-md ignored

    # commands/
    (root / "commands").mkdir(parents=True)
    (root / "commands" / "eval-run.md").write_text("# eval\n")

    # hooks/: .py + .sh kept; test_*.py and other suffixes skipped
    (root / "hooks").mkdir(parents=True)
    (root / "hooks" / "guard.py").write_text("# guard\n")
    (root / "hooks" / "deploy.sh").write_text("# deploy\n")
    (root / "hooks" / "test_guard.py").write_text("# test - skipped\n")
    (root / "hooks" / "hooks.json").write_text("{}\n")  # non-.py/.sh skipped

    # codex/skills/
    (root / "codex" / "skills" / "codex-orchestra").mkdir(parents=True)
    (root / "codex" / "skills" / "loose.txt").write_text("not a dir entry\n")


@pytest.fixture()
def fake_repo(tmp_path, monkeypatch):
    """Point the module's path globals at a synthetic tree under tmp_path."""
    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root)
    score = root / ".planning" / "score"
    out = root / "dashboard" / "data.js"
    arch = root / "dashboard" / "architecture.html"
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m, "SCORE_DIR", score)
    monkeypatch.setattr(m, "OUT", out)
    monkeypatch.setattr(m, "ARCH_HTML_OUT", arch)
    return root


# --------------------------------------------------------------------------- #
# collect_assets
# --------------------------------------------------------------------------- #
def test_collect_assets_returns_all_five_types(fake_repo):
    assets = m.collect_assets()
    types = {a["type"] for a in assets}
    # all five top-level asset families present
    assert {"skill", "agent", "command", "hook", "codex-skill"} <= types
    # every entry has exactly the expected fields
    for a in assets:
        assert set(a.keys()) == {"type", "name"}
        assert isinstance(a["name"], str) and a["name"]


def test_collect_assets_skill_shell_branch(fake_repo):
    assets = m.collect_assets()
    by_name = {a["name"]: a["type"] for a in assets}
    assert by_name["doc-management"] == "skill"        # has SKILL.md
    assert by_name["auto-pilot"] == "skill"            # has SKILL.md
    assert by_name["deprecated-shell"] == "skill-shell"  # dir w/o SKILL.md
    assert "stray.txt" not in by_name  # non-dir under skills/ ignored


def test_collect_assets_hook_filtering(fake_repo):
    assets = m.collect_assets()
    hook_names = {a["name"] for a in assets if a["type"] == "hook"}
    assert hook_names == {"guard.py", "deploy.sh"}  # test_*.py + .json excluded


def test_collect_assets_agents_and_commands(fake_repo):
    assets = m.collect_assets()
    agents = {a["name"] for a in assets if a["type"] == "agent"}
    commands = {a["name"] for a in assets if a["type"] == "command"}
    assert agents == {"pm-orchestrator", "auto-pilot-codex-reviewer", "tech-critic"}
    assert "not-md.txt" not in agents  # non-md ignored
    assert commands == {"eval-run"}


def test_collect_assets_codex_skills_dirs_only(fake_repo):
    assets = m.collect_assets()
    codex = {a["name"] for a in assets if a["type"] == "codex-skill"}
    assert codex == {"codex-orchestra"}  # loose.txt (file, not dir) excluded


def test_collect_assets_missing_dirs_tolerated(tmp_path, monkeypatch):
    """No skills/agents/etc. dirs at all -> empty list, no crash."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(m, "ROOT", empty)
    assert m.collect_assets() == []


def test_collect_assets_real_repo_smoke():
    """Against the actual repo, all five families exist (no monkeypatch)."""
    assets = m.collect_assets()
    types = {a["type"] for a in assets}
    assert {"skill", "agent", "command", "hook", "codex-skill"} <= types


# --------------------------------------------------------------------------- #
# subsystem_of classification rules
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name, expected",
    [
        ("doc-management", "docs-core"),
        ("vault-build", "docs-vault-export"),
        ("nbm-to-obsidian", "docs-vault-export"),
        ("harness", "harness"),
        ("setup-harness", "harness"),
        ("setup-claude-md", "harness"),
        ("quality-eval", "quality"),
        ("adversarial-review-loop", "quality"),
        ("residue-audit", "quality"),
        ("code-perfector", "quality"),
        ("auto-pilot", "core-loop"),
        ("eval-run", "core-loop"),
        ("worker", "core-loop"),
        ("pm-orchestrator", "core-loop"),
        ("retro", "core-loop"),
        ("tech-critic", "review"),
        ("review-gatekeeper", "review"),
        ("specialist-pool", "review"),
        ("sha-deploy-init", "deploy"),
        ("deploy", "deploy"),
        ("goal-buddy", "goal"),
        ("totally-unknown-thing", "other"),
    ],
)
def test_subsystem_classification(name, expected):
    assert m.subsystem_of(name) == expected


def test_reviewer_quirk_pinned():
    """PRE-EXISTING QUIRK (pinned, not fixed): auto-pilot-*-reviewer agents
    classify as 'core-loop', NOT 'review'. The SUBSYSTEM_RULES list is
    evaluated top-to-bottom and the `^(auto-pilot|...)` rule (-> core-loop)
    sits ABOVE the `(reviewer|...)` rule (-> review), so the auto-pilot prefix
    wins for the reviewer agents. This test documents current behavior; if the
    rule order is ever intentionally changed, update this assertion."""
    assert m.subsystem_of("auto-pilot-codex-reviewer") == "core-loop"
    assert m.subsystem_of("auto-pilot-claude-reviewer") == "core-loop"
    # A reviewer name WITHOUT the auto-pilot prefix does hit the review rule:
    assert m.subsystem_of("codex-reviewer") == "review"


# --------------------------------------------------------------------------- #
# weighted scoring
# --------------------------------------------------------------------------- #
def test_weighted_full_scores_to_ten():
    assert m.weighted({"core_fit": 10, "uniqueness": 10, "evidence": 10, "cost": 10}) == 10.0


def test_weighted_uses_correct_factors():
    # core_fit only: 5 * 0.4 = 2.0
    assert m.weighted({"core_fit": 5}) == 2.0
    # uniqueness only: 8 * 0.25 = 2.0
    assert m.weighted({"uniqueness": 8}) == 2.0
    # evidence only: 5 * 0.2 = 1.0
    assert m.weighted({"evidence": 5}) == 1.0
    # cost only: 10 * 0.15 = 1.5
    assert m.weighted({"cost": 10}) == 1.5


def test_weighted_nonnumeric_and_missing_coerce_to_zero():
    assert m.weighted({}) == 0.0
    assert m.weighted({"core_fit": "oops", "uniqueness": 4}) == 1.0  # 4*0.25


# --------------------------------------------------------------------------- #
# load_rounds
# --------------------------------------------------------------------------- #
def test_load_rounds_reads_sorted_valid_json(fake_repo):
    score = m.SCORE_DIR
    score.mkdir(parents=True)
    (score / "round-0.json").write_text(json.dumps({"round": 0, "label": "a"}))
    (score / "round-1.json").write_text(json.dumps({"round": 1, "label": "b"}))
    rounds = m.load_rounds()
    assert [r["round"] for r in rounds] == [0, 1]


def test_load_rounds_skips_malformed_and_nondict(fake_repo):
    score = m.SCORE_DIR
    score.mkdir(parents=True)
    (score / "round-0.json").write_text("{not valid json")
    (score / "round-1.json").write_text("[1, 2, 3]")  # valid json but not a dict
    (score / "round-2.json").write_text(json.dumps({"round": 2}))
    rounds = m.load_rounds()
    assert rounds == [{"round": 2}]


def test_load_rounds_no_score_dir(fake_repo):
    # SCORE_DIR does not exist in fake_repo by default
    assert not m.SCORE_DIR.exists()
    assert m.load_rounds() == []


# --------------------------------------------------------------------------- #
# build_architecture_html
# --------------------------------------------------------------------------- #
def test_build_architecture_html_non_empty_with_markers(fake_repo):
    assets = m.collect_assets()
    counts: dict[str, int] = {}
    for a in assets:
        counts[a["type"]] = counts.get(a["type"], 0) + 1
    html = m.build_architecture_html(assets, counts, "abc123", "feat/x", "2026-06-07")
    assert html.startswith("<!DOCTYPE html>")
    assert len(html) > 1000
    # section markers from the template
    for marker in (
        "auto-pilot — Architecture",
        "Asset counts",
        "4-Pillar purpose",
        "Coding-loop process",
        "Binding contracts",
        "Asset → pillar mapping",
    ):
        assert marker in html
    # metadata interpolated
    assert "abc123" in html
    assert "feat/x" in html
    assert "2026-06-07" in html
    # pillar labels rendered
    assert "P① 자율 코딩 루프" in html
    # a known asset appears in the live mapping table
    assert "doc-management" in html
    # all binding-contract names present
    for cname, _, _ in m.BINDING_CONTRACTS:
        assert cname in html


def test_build_architecture_html_escapes_special_chars(fake_repo):
    assets = [{"type": "skill", "name": "x<y&z\"q"}]
    counts = {"skill": 1}
    html = m.build_architecture_html(assets, counts, "h", "b", "g")
    assert "x&lt;y&amp;z&quot;q" in html
    assert "x<y&z" not in html  # raw unescaped form must not leak


def test_esc_helper():
    assert m._esc('<a href="x">&') == "&lt;a href=&quot;x&quot;&gt;&amp;"


# --------------------------------------------------------------------------- #
# main() end-to-end against the fake tree (never touches real dashboard/)
# --------------------------------------------------------------------------- #
def test_main_writes_data_js_and_architecture_html(fake_repo, monkeypatch, capsys):
    # add a round file so the rounds-merge loop (weighted enrichment) runs
    score = m.SCORE_DIR
    score.mkdir(parents=True)
    (score / "round-0.json").write_text(
        json.dumps(
            {
                "round": 0,
                "label": "provisional",
                "assets": {
                    "skill:doc-management": {
                        "core_fit": 10,
                        "uniqueness": 8,
                        "evidence": 6,
                        "cost": 10,
                        "verdict": "CORE",
                    }
                },
            }
        )
    )

    # stub git calls so the test is deterministic + offline
    class _R:
        def __init__(self, out: str) -> None:
            self.stdout = out

    def fake_run(args, **kwargs):
        if "rev-parse" in args:
            return _R("deadbee\n")
        if "branch" in args:
            return _R("test-branch\n")
        return _R("\n")

    monkeypatch.setattr(m.subprocess, "run", fake_run)

    m.main()

    # outputs landed in the fake tree, NOT the real repo dashboard/
    assert m.OUT.exists()
    assert m.ARCH_HTML_OUT.exists()

    data_text = m.OUT.read_text()
    assert data_text.startswith("window.DASHBOARD_DATA = ")
    assert data_text.rstrip().endswith(";")
    payload = json.loads(
        data_text.split("window.DASHBOARD_DATA = ", 1)[1].rstrip().rstrip(";")
    )
    assert payload["branch"] == "test-branch"
    assert payload["commit"] == "deadbee"
    assert payload["counts"]  # type->count map populated
    # asset rows carry the subsystem enrichment
    assert all("subsystem" in a for a in payload["assets"])
    # weighted total injected into round asset scores
    rnd_asset = payload["rounds"][0]["assets"]["skill:doc-management"]
    assert rnd_asset["total"] == m.weighted(rnd_asset)

    arch = m.ARCH_HTML_OUT.read_text()
    assert arch.startswith("<!DOCTYPE html>")
    assert "deadbee" in arch and "test-branch" in arch

    captured = capsys.readouterr().out
    assert "wrote" in captured


def test_main_does_not_write_real_repo_dashboard(monkeypatch, tmp_path):
    """Belt-and-suspenders: even main()'s OUT.parent.mkdir must target the fake
    tree. We assert the real repo data.js mtime is untouched by a fake-tree run."""
    real_out = Path(m.__file__).resolve().parents[1] / "dashboard" / "data.js"
    before = real_out.stat().st_mtime_ns if real_out.exists() else None

    root = tmp_path / "repo"
    root.mkdir()
    _make_tree(root)
    monkeypatch.setattr(m, "ROOT", root)
    monkeypatch.setattr(m, "SCORE_DIR", root / ".planning" / "score")
    monkeypatch.setattr(m, "OUT", root / "dashboard" / "data.js")
    monkeypatch.setattr(m, "ARCH_HTML_OUT", root / "dashboard" / "architecture.html")
    monkeypatch.setattr(
        m.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "x\n"})()
    )

    m.main()

    after = real_out.stat().st_mtime_ns if real_out.exists() else None
    assert before == after  # real dashboard/data.js untouched

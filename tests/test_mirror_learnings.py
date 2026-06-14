"""Tests for scripts/_mirror_learnings.py — idempotent one-way vault gotcha mirror.

Anti-fabrication: all tests seed REAL schema-valid tickets into a temp ledger
dir (via bump_or_create or direct _valid_ticket helpers matching the real miner
shape), then invoke the REAL mirror() / select_promotable() and assert on the
pages they write.  No hand-authored gotcha pages are asserted against.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _improvement as imp
import _mirror_learnings as ml


# ---------------------------------------------------------------------------
# Helpers — build schema-valid tickets without re-inventing the miner
# ---------------------------------------------------------------------------

def _evidence_entry(
    run_id: str = "run-1",
    snippet: str = "worker skipped verify",
    source_path: str = "",
) -> dict:
    entry: dict = {"run_id": run_id, "snippet": snippet}
    if source_path:
        entry["source_path"] = source_path
    return entry


def _valid_ticket(
    fingerprint: str = "a" * 64,
    state: str = "candidate",
    source: str = "reviewer-finding",
    distinct_runs: int = 2,
    pattern: str = "worker skipped verify gate",
    candidate_asset: str | None = "hook",
) -> dict:
    """Build a schema-valid ticket.

    ``source="reviewer-finding"`` + ``distinct_runs=2`` passes ``is_promotable()``
    (threshold=2).  Use ``state="promoted"`` for the fully-promoted path.
    Use ``distinct_runs=1`` for sub-threshold.
    """
    evidence_count = distinct_runs
    evidence = [
        _evidence_entry(run_id=f"run-{i}", snippet=f"snippet-{i}")
        for i in range(1, evidence_count + 1)
    ]
    gates: dict = {"tests_pass": None, "ci_pass": None, "user_approved": None}
    if state == "promoted":
        gates = {"tests_pass": True, "ci_pass": True, "user_approved": True}
    return {
        "schema_version": 1,
        "fingerprint": fingerprint,
        "state": state,
        "pattern": pattern,
        "source": source,
        "candidate_asset": candidate_asset,
        "occurrences": evidence_count,
        "distinct_runs": evidence_count,
        "first_seen": "2026-06-09T00:00:00Z",
        "last_seen": "2026-06-14T00:00:00Z",
        "plugin_version": "0.9.0",
        "repo_fingerprint": "abc123",
        "evidence": evidence,
        "promotion_gate": gates,
    }


def _write_ticket(ledger: Path, ticket: dict) -> None:
    ledger.mkdir(parents=True, exist_ok=True)
    fp = ticket["fingerprint"]
    imp.validate_ticket(ticket)  # anti-fabrication: assert schema-valid before writing
    (ledger / f"{fp}.json").write_text(json.dumps(ticket, indent=2) + "\n")


# ---------------------------------------------------------------------------
# 1. N promotable tickets → exactly N gotcha pages; fingerprint round-trip
# ---------------------------------------------------------------------------

def test_mirror_writes_promotable_tickets(tmp_path):
    """A promoted ticket + a reviewer-finding with distinct_runs>=2 → two pages.

    Each page's frontmatter ``fingerprint`` matches the ticket's full fingerprint.
    """
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"

    fp_a = "a" * 64
    fp_b = "b" * 64
    promoted = _valid_ticket(fingerprint=fp_a, state="promoted", distinct_runs=2)
    reviewer = _valid_ticket(fingerprint=fp_b, state="candidate", distinct_runs=2)
    _write_ticket(ledger, promoted)
    _write_ticket(ledger, reviewer)

    counts = ml.mirror(ledger, vault)

    gotchas_dir = vault / "gotchas"
    pages = list(gotchas_dir.glob("gotcha-*.md"))
    assert len(pages) == 2, f"expected 2 pages, got {len(pages)}: {[p.name for p in pages]}"
    assert counts["written"] == 2
    assert counts["unchanged"] == 0
    assert counts["pruned"] == 0

    # Links-back requirement: frontmatter fingerprint == ticket fingerprint
    for page in pages:
        text = page.read_text()
        assert "---" in text
        fp_line = next(
            (ln for ln in text.splitlines() if ln.startswith("fingerprint:")), None
        )
        assert fp_line is not None, f"no fingerprint in {page.name}"
        page_fp = fp_line.split(":", 1)[1].strip()
        assert page_fp in (fp_a, fp_b), f"unexpected fingerprint {page_fp}"
        assert page.name == f"gotcha-{page_fp}.md"


# ---------------------------------------------------------------------------
# 2. Byte-stable re-run
# ---------------------------------------------------------------------------

def test_mirror_byte_stable_rerun(tmp_path):
    """Running mirror twice produces identical bytes; second run reports written=0."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    ticket = _valid_ticket(fingerprint="c" * 64, state="candidate", distinct_runs=2)
    _write_ticket(ledger, ticket)

    ml.mirror(ledger, vault)
    page = vault / "gotchas" / f"gotcha-{'c' * 64}.md"
    assert page.exists()
    first_bytes = page.read_bytes()

    counts2 = ml.mirror(ledger, vault)

    assert page.read_bytes() == first_bytes, "page bytes changed between runs"
    assert counts2["written"] == 0
    assert counts2["unchanged"] == 1


# ---------------------------------------------------------------------------
# 3. Un-promotable tickets produce no pages
# ---------------------------------------------------------------------------

def test_mirror_excludes_sub_threshold_candidate(tmp_path):
    """Candidate with distinct_runs=1 is below reviewer-finding threshold (2)."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    ticket = _valid_ticket(fingerprint="d" * 64, state="candidate", distinct_runs=1)
    _write_ticket(ledger, ticket)

    counts = ml.mirror(ledger, vault)

    pages = list((vault / "gotchas").glob("gotcha-*.md")) if (vault / "gotchas").exists() else []
    assert pages == []
    assert counts["written"] == 0


def test_mirror_excludes_rejected_ticket(tmp_path):
    """Rejected tickets are never mirrored even if distinct_runs >= threshold."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    ticket = _valid_ticket(fingerprint="e" * 64, state="rejected", distinct_runs=3)
    _write_ticket(ledger, ticket)

    counts = ml.mirror(ledger, vault)

    pages = list((vault / "gotchas").glob("gotcha-*.md")) if (vault / "gotchas").exists() else []
    assert pages == []
    assert counts["written"] == 0


# ---------------------------------------------------------------------------
# 4. Prune: page disappears when ticket transitions to rejected
# ---------------------------------------------------------------------------

def test_mirror_prunes_page_when_ticket_rejected(tmp_path):
    """Mirror a promotable ticket → page exists; flip to rejected → re-mirror → page gone."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    fp = "f" * 64
    ticket = _valid_ticket(fingerprint=fp, state="candidate", distinct_runs=2)
    _write_ticket(ledger, ticket)

    counts1 = ml.mirror(ledger, vault)
    assert counts1["written"] == 1
    assert (vault / "gotchas" / f"gotcha-{fp}.md").exists()

    # Flip to rejected on disk
    rejected = dict(ticket)
    rejected["state"] = "rejected"
    (ledger / f"{fp}.json").write_text(json.dumps(rejected, indent=2) + "\n")

    counts2 = ml.mirror(ledger, vault)
    assert counts2["pruned"] >= 1
    assert not (vault / "gotchas" / f"gotcha-{fp}.md").exists(), "page should be pruned"


# ---------------------------------------------------------------------------
# 5. Human page safety: hand-written pages are never touched
# ---------------------------------------------------------------------------

def test_mirror_leaves_human_page_untouched(tmp_path):
    """A page without the generator sentinel is never removed."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    gotchas_dir = vault / "gotchas"
    gotchas_dir.mkdir(parents=True, exist_ok=True)

    human_page = gotchas_dir / "my-note.md"
    human_content = "# Hand-written note\n\nThis is a human page.\n"
    human_page.write_text(human_content)

    # Seed one promotable ticket
    ticket = _valid_ticket(fingerprint="1" * 64, state="candidate", distinct_runs=2)
    _write_ticket(ledger, ticket)

    counts = ml.mirror(ledger, vault)

    assert human_page.exists(), "human page must not be deleted"
    assert human_page.read_text() == human_content, "human page bytes must be unchanged"
    assert counts["skipped_human"] >= 1


# ---------------------------------------------------------------------------
# 6. Dry-run writes nothing
# ---------------------------------------------------------------------------

def test_mirror_dry_run_writes_nothing(tmp_path):
    """dry_run=True computes counts but touches no disk."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    ticket = _valid_ticket(fingerprint="2" * 64, state="candidate", distinct_runs=2)
    _write_ticket(ledger, ticket)

    counts = ml.mirror(ledger, vault, dry_run=True)

    # gotchas_dir must NOT have been created
    assert not (vault / "gotchas").exists(), "dry_run must not create the gotchas dir"
    assert counts["written"] == 1  # would-be writes are counted
    assert counts["unchanged"] == 0


def test_mirror_dry_run_no_ledger(tmp_path):
    """dry_run with absent ledger returns zero counts and exits 0."""
    vault = tmp_path / "vault"
    counts = ml.mirror(tmp_path / "no-ledger", vault, dry_run=True)
    assert counts == {"written": 0, "unchanged": 0, "pruned": 0, "skipped_human": 0}


# ---------------------------------------------------------------------------
# 7. Vault resolution precedence
# ---------------------------------------------------------------------------

def test_resolve_vault_nbm_vault_path_wins(tmp_path, monkeypatch):
    """NBM_VAULT_PATH takes priority over all other env vars."""
    expected = tmp_path / "nbm-vault"
    monkeypatch.setenv("NBM_VAULT_PATH", str(expected))
    monkeypatch.setenv("VAULT_BUILDER_VAULT", str(tmp_path / "vb-vault"))
    monkeypatch.setenv("VB_OBSIDIAN_ROOT", str(tmp_path / "obsidian"))

    result = ml.resolve_vault(Path("/some/repo"))
    assert result == expected


def test_resolve_vault_vb_builder_fallback(tmp_path, monkeypatch):
    """VAULT_BUILDER_VAULT is used when NBM_VAULT_PATH is absent."""
    expected = tmp_path / "vb-vault"
    monkeypatch.delenv("NBM_VAULT_PATH", raising=False)
    monkeypatch.setenv("VAULT_BUILDER_VAULT", str(expected))
    monkeypatch.setenv("VB_OBSIDIAN_ROOT", str(tmp_path / "obsidian"))

    result = ml.resolve_vault(Path("/some/repo"))
    assert result == expected


def test_resolve_vault_obsidian_root_fallback(tmp_path, monkeypatch):
    """VB_OBSIDIAN_ROOT/<basename> used when neither NBM nor VB vault is set."""
    obsidian = tmp_path / "obsidian"
    repo_root = Path("/projects/my-repo")
    monkeypatch.delenv("NBM_VAULT_PATH", raising=False)
    monkeypatch.delenv("VAULT_BUILDER_VAULT", raising=False)
    monkeypatch.setenv("VB_OBSIDIAN_ROOT", str(obsidian))

    result = ml.resolve_vault(repo_root)
    assert result == obsidian / "my-repo"


def test_resolve_vault_home_documents_obsidian_default(tmp_path, monkeypatch):
    """Falls back to $HOME/Documents/Obsidian/<basename> when nothing is set."""
    monkeypatch.delenv("NBM_VAULT_PATH", raising=False)
    monkeypatch.delenv("VAULT_BUILDER_VAULT", raising=False)
    monkeypatch.delenv("VB_OBSIDIAN_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    repo_root = Path("/projects/auto-pilot")
    result = ml.resolve_vault(repo_root)
    assert result == tmp_path / "Documents" / "Obsidian" / "auto-pilot"


# ---------------------------------------------------------------------------
# 8. select_promotable: absent ledger returns []
# ---------------------------------------------------------------------------

def test_select_promotable_absent_ledger_returns_empty(tmp_path):
    assert ml.select_promotable(tmp_path / "no-ledger") == []


# ---------------------------------------------------------------------------
# 9. CLI smoke via orchestrator (uses real bump_or_create chain)
# ---------------------------------------------------------------------------

def test_orchestrator_improvements_mirror_dry_run_no_ledger(tmp_path, monkeypatch, capsys):
    """improvements-mirror --dry-run exits 0 with empty counts when no ledger exists."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NBM_VAULT_PATH", str(tmp_path / "vault"))

    import orchestrator
    rc = orchestrator.main([
        "improvements-mirror",
        "--repo-root", str(tmp_path / "repo"),
        "--dry-run",
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    counts = json.loads(out)
    assert counts["written"] == 0
    assert counts["pruned"] == 0


def test_orchestrator_improvements_mirror_real_ticket(tmp_path, monkeypatch, capsys):
    """improvements-mirror with a real promotable ticket → one page written via CLI."""
    # Build ledger via bump_or_create (real miner chain — anti-fabrication)
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    vault = tmp_path / "vault"

    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("NBM_VAULT_PATH", str(vault))

    slug = str(repo_root.resolve()).replace("/", "-")
    ledger = tmp_path / "home" / ".claude" / "projects" / slug / "improvements"
    ledger.mkdir(parents=True, exist_ok=True)

    now = datetime(2026, 6, 14, 12, 0, 0, tzinfo=timezone.utc)
    for run_num in range(1, 3):
        obs = imp.Observation(
            source="reviewer-finding",
            file_basename="orchestrator.py",
            issue="mirror smoke test issue",
            candidate_asset="hook",
            run_id=f"smoke-run-{run_num}",
            snippet=f"snippet {run_num}",
            source_path="scripts/orchestrator.py",
        )
        imp.bump_or_create(ledger, obs, repo_root=repo_root, now=now, dry_run=False)

    import orchestrator
    rc = orchestrator.main([
        "improvements-mirror",
        "--repo-root", str(repo_root),
        "--vault", str(vault),
    ])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    counts = json.loads(out)
    assert counts["written"] == 1
    pages = list((vault / "gotchas").glob("gotcha-*.md"))
    assert len(pages) == 1
    # Verify sentinel is in the written page
    content = pages[0].read_text()
    assert f"generator: {ml.GENERATOR}" in content


# ---------------------------------------------------------------------------
# 10. YAML injection guard: newlines in pattern/snippet don't break frontmatter
# ---------------------------------------------------------------------------

def test_render_gotcha_yaml_injection_guard(tmp_path):
    """Newlines in pattern text must not inject extra YAML keys."""
    ticket = _valid_ticket(
        fingerprint="9" * 64,
        state="candidate",
        distinct_runs=2,
        pattern="bad pattern\ninjected: evil",
    )
    content = ml.render_gotcha(ticket)
    # The injected YAML key must not appear as a real frontmatter key
    frontmatter_end = content.find("\n---\n", 4)
    frontmatter = content[:frontmatter_end]
    assert "injected: evil" not in frontmatter


# ---------------------------------------------------------------------------
# 11. Fix 1 — PRUNE-ON-UNLOADABLE-LEDGER safety regressions
# ---------------------------------------------------------------------------

def test_mirror_absent_ledger_leaves_owned_page_intact(tmp_path):
    """Owned page survives when the ledger directory does not exist at all."""
    vault = tmp_path / "vault"
    gotchas_dir = vault / "gotchas"

    # Write a genuinely owned page using render_gotcha so sentinel is real.
    ticket = _valid_ticket(fingerprint="a" * 64, state="candidate", distinct_runs=2)
    owned_content = ml.render_gotcha(ticket)
    gotchas_dir.mkdir(parents=True)
    owned_page = gotchas_dir / ml.gotcha_filename(ticket)
    owned_page.write_text(owned_content, encoding="utf-8")

    absent_ledger = tmp_path / "no-ledger-dir"
    counts = ml.mirror(absent_ledger, vault)

    assert owned_page.exists(), "owned page must not be deleted when ledger is absent"
    assert owned_page.read_text(encoding="utf-8") == owned_content
    assert counts["pruned"] == 0


def test_mirror_unloadable_ledger_leaves_owned_page_intact(tmp_path):
    """Owned page survives when ledger path points to a file (not a dir) so load_tickets raises."""
    vault = tmp_path / "vault"
    gotchas_dir = vault / "gotchas"

    ticket = _valid_ticket(fingerprint="b" * 64, state="candidate", distinct_runs=2)
    owned_content = ml.render_gotcha(ticket)
    gotchas_dir.mkdir(parents=True)
    owned_page = gotchas_dir / ml.gotcha_filename(ticket)
    owned_page.write_text(owned_content, encoding="utf-8")

    # Point ledger at a regular file so load_tickets raises a dir-level error.
    fake_ledger = tmp_path / "ledger-is-a-file"
    fake_ledger.write_text("not a dir\n")

    counts = ml.mirror(fake_ledger, vault)

    assert owned_page.exists(), "owned page must not be deleted when ledger is unreadable"
    assert owned_page.read_text(encoding="utf-8") == owned_content
    assert counts["pruned"] == 0


def test_mirror_authoritative_rejected_ledger_prunes_owned_page(tmp_path):
    """Authoritative ledger with all tickets rejected → owned page IS pruned."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    fp = "c" * 64

    # First mirror with a promotable ticket to create the owned page.
    ticket = _valid_ticket(fingerprint=fp, state="candidate", distinct_runs=2)
    _write_ticket(ledger, ticket)
    counts1 = ml.mirror(ledger, vault)
    assert counts1["written"] == 1
    owned_page = vault / "gotchas" / f"gotcha-{fp}.md"
    assert owned_page.exists()

    # Flip to rejected (authoritative empty ledger after filter).
    rejected = dict(ticket)
    rejected["state"] = "rejected"
    (ledger / f"{fp}.json").write_text(json.dumps(rejected, indent=2) + "\n")

    counts2 = ml.mirror(ledger, vault)
    assert counts2["pruned"] >= 1
    assert not owned_page.exists(), "owned page should be pruned on authoritative rejected ledger"


# ---------------------------------------------------------------------------
# 12. Fix 2 — SENTINEL STRICT OWNERSHIP regressions
# ---------------------------------------------------------------------------

def test_is_owned_page_no_generator_line_survives(tmp_path):
    """Filename-shaped page without any generator line is treated as human → not owned."""
    fp = "d" * 64
    page = tmp_path / f"gotcha-{fp}.md"
    page.write_text(
        "---\ntype: gotcha\nderived: true\n---\n\n# Human page\nNo generator line here.\n",
        encoding="utf-8",
    )
    assert not ml._is_owned_page(page)


def test_mirror_human_page_no_generator_survives_prune(tmp_path):
    """Filename-shaped page with no generator: line survives an authoritative-empty prune."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    gotchas_dir = vault / "gotchas"
    gotchas_dir.mkdir(parents=True)

    fp = "d" * 64
    human_page = gotchas_dir / f"gotcha-{fp}.md"
    human_content = "---\ntype: gotcha\nderived: true\n---\n\n# Human page\nNo generator.\n"
    human_page.write_text(human_content, encoding="utf-8")

    # Write a rejected ticket so ledger is authoritative but empty of promotable.
    rejected = _valid_ticket(fingerprint="e" * 64, state="rejected", distinct_runs=2)
    _write_ticket(ledger, rejected)

    counts = ml.mirror(ledger, vault)

    assert human_page.exists(), "filename-shaped human page must survive authoritative prune"
    assert human_page.read_text(encoding="utf-8") == human_content
    assert counts["skipped_human"] >= 1


def test_is_owned_page_foreign_generator_not_owned(tmp_path):
    """Page with generator: something-else is NOT owned."""
    fp = "e" * 64
    page = tmp_path / f"gotcha-{fp}.md"
    page.write_text(
        "---\ntype: gotcha\ngenerator: something-else\n---\n\n# Foreign page\n",
        encoding="utf-8",
    )
    assert not ml._is_owned_page(page)


def test_mirror_foreign_generator_page_survives(tmp_path):
    """Page with foreign generator survives an authoritative prune run."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    gotchas_dir = vault / "gotchas"
    gotchas_dir.mkdir(parents=True)

    fp = "e" * 64
    foreign_page = gotchas_dir / f"gotcha-{fp}.md"
    foreign_content = "---\ntype: gotcha\ngenerator: something-else\n---\n\n# Foreign\n"
    foreign_page.write_text(foreign_content, encoding="utf-8")

    rejected = _valid_ticket(fingerprint="f" * 64, state="rejected", distinct_runs=2)
    _write_ticket(ledger, rejected)

    counts = ml.mirror(ledger, vault)

    assert foreign_page.exists(), "foreign-generator page must survive"
    assert foreign_page.read_text(encoding="utf-8") == foreign_content
    assert counts["skipped_human"] >= 1


def test_is_owned_page_multiline_generator_not_owned(tmp_path):
    """Multi-line plain scalar: first line matches but continuation makes it non-exact → not owned.

    PyYAML parses the value as '_mirror_learnings trailing' which != GENERATOR.
    """
    fp = "f" * 64
    page = tmp_path / f"gotcha-{fp}.md"
    # YAML plain scalar with indented continuation — value becomes "_mirror_learnings trailing"
    page.write_text(
        f"---\ntype: gotcha\ngenerator: {ml.GENERATOR}\n  trailing\n---\n\n# Multi-line\n",
        encoding="utf-8",
    )
    assert not ml._is_owned_page(page), (
        "multi-line generator scalar must not match exact GENERATOR string"
    )


def test_mirror_multiline_generator_page_survives(tmp_path):
    """Page with multi-line generator: value survives an authoritative prune run."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    gotchas_dir = vault / "gotchas"
    gotchas_dir.mkdir(parents=True)

    fp = "f" * 64
    multiline_page = gotchas_dir / f"gotcha-{fp}.md"
    multiline_content = (
        f"---\ntype: gotcha\ngenerator: {ml.GENERATOR}\n  trailing\n---\n\n# Multi-line\n"
    )
    multiline_page.write_text(multiline_content, encoding="utf-8")

    rejected = _valid_ticket(fingerprint="0" * 64, state="rejected", distinct_runs=2)
    _write_ticket(ledger, rejected)

    counts = ml.mirror(ledger, vault)

    assert multiline_page.exists(), "multi-line generator page must not be pruned"
    assert multiline_page.read_text(encoding="utf-8") == multiline_content
    assert counts["skipped_human"] >= 1


def test_mirror_genuinely_owned_page_pruned_when_ticket_gone(tmp_path):
    """A genuinely owned page (produced by render_gotcha/mirror) is pruned when its ticket is gone."""
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    fp = "7" * 64

    # Seed promotable ticket, mirror it to create owned page.
    ticket = _valid_ticket(fingerprint=fp, state="candidate", distinct_runs=2)
    _write_ticket(ledger, ticket)
    counts1 = ml.mirror(ledger, vault)
    assert counts1["written"] == 1
    owned_page = vault / "gotchas" / f"gotcha-{fp}.md"
    assert owned_page.exists()
    assert ml._is_owned_page(owned_page), "page produced by mirror must pass _is_owned_page"

    # Remove ticket from ledger so promotable list is now empty (authoritative).
    (ledger / f"{fp}.json").unlink()

    # Add a rejected ticket so ledger dir is non-empty (load_tickets runs, returns []).
    rejected = _valid_ticket(fingerprint="8" * 64, state="rejected", distinct_runs=2)
    _write_ticket(ledger, rejected)

    counts2 = ml.mirror(ledger, vault)
    assert counts2["pruned"] >= 1, "owned page should be pruned when ticket is gone"
    assert not owned_page.exists()


# ---------------------------------------------------------------------------
# 13. Fix 3 — CORRUPT TICKET blocks prune (partial-corrupt ledger safety)
# ---------------------------------------------------------------------------

def test_mirror_corrupt_ticket_blocks_prune_of_unrelated_owned_page(tmp_path):
    """A corrupt ticket in the ledger sets authoritative=False → prune is skipped.

    Seed: one VALID promotable ticket (fp_valid) + one CORRUPT *.json file (fp_corrupt
    with 64-hex stem but invalid JSON content).  Also pre-seed an owned gotcha page for
    a third fingerprint (fp_orphan) whose ticket is not in the ledger at all.  On a
    fully-authoritative run the orphan page would be pruned.  With the corrupt ticket
    present the ledger is not trustworthy, so authoritative=False and the orphan page
    MUST survive (pruned == 0).  The valid ticket's page must still be written.
    """
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    gotchas_dir = vault / "gotchas"

    fp_valid = "a" * 64
    fp_corrupt = "b" * 64  # 64 hex chars — realistic filename shape
    fp_orphan = "c" * 64   # owned page with no corresponding ledger ticket

    # Seed valid promotable ticket.
    valid_ticket = _valid_ticket(fingerprint=fp_valid, state="candidate", distinct_runs=2)
    _write_ticket(ledger, valid_ticket)

    # Seed corrupt JSON file with a realistic 64-hex-stem filename.
    (ledger / f"{fp_corrupt}.json").write_text("{ not valid json", encoding="utf-8")

    # Pre-seed an owned gotcha page for fp_orphan (no ticket in ledger).
    orphan_ticket = _valid_ticket(fingerprint=fp_orphan, state="candidate", distinct_runs=2)
    orphan_content = ml.render_gotcha(orphan_ticket)
    gotchas_dir.mkdir(parents=True)
    orphan_page = gotchas_dir / ml.gotcha_filename(orphan_ticket)
    orphan_page.write_text(orphan_content, encoding="utf-8")
    assert ml._is_owned_page(orphan_page), "orphan page must be recognized as owned"

    counts = ml.mirror(ledger, vault)

    # Valid ticket's page must be written (writes are always safe regardless of authoritative).
    assert counts["written"] == 1, f"expected 1 written, got {counts}"
    assert (gotchas_dir / f"gotcha-{fp_valid}.md").exists(), "valid ticket page must be written"

    # Corrupt ticket → authoritative=False → prune SKIPPED → orphan page survives.
    assert counts["pruned"] == 0, (
        f"corrupt ledger must suppress prune, got pruned={counts['pruned']}"
    )
    assert orphan_page.exists(), (
        "orphan owned page must survive when ledger has a corrupt ticket"
    )
    assert orphan_page.read_bytes() == orphan_content.encode("utf-8"), (
        "orphan page bytes must be unchanged"
    )


def test_mirror_clean_ledger_still_prunes_on_authoritative_empty(tmp_path):
    """Authoritative clean ledger with all tickets rejected → stale owned page IS pruned.

    This confirms the corrupt-ticket fix did not disable legitimate pruning on a
    fully-parseable ledger.  Mirrors the scenario from
    test_mirror_authoritative_rejected_ledger_prunes_owned_page but is
    self-contained so the contract of section 13 is explicit.
    """
    ledger = tmp_path / "ledger"
    vault = tmp_path / "vault"
    fp = "d" * 64

    # Step 1: mirror a promotable ticket to create the owned page.
    ticket = _valid_ticket(fingerprint=fp, state="candidate", distinct_runs=2)
    _write_ticket(ledger, ticket)
    counts1 = ml.mirror(ledger, vault)
    assert counts1["written"] == 1
    owned_page = vault / "gotchas" / f"gotcha-{fp}.md"
    assert owned_page.exists()

    # Step 2: flip to rejected (all tickets now non-promotable; clean parse → authoritative=True).
    rejected = dict(ticket)
    rejected["state"] = "rejected"
    (ledger / f"{fp}.json").write_text(json.dumps(rejected, indent=2) + "\n")

    counts2 = ml.mirror(ledger, vault)

    assert counts2["pruned"] >= 1, (
        "clean authoritative ledger with rejected tickets must still prune stale pages"
    )
    assert not owned_page.exists(), "stale owned page must be gone after authoritative prune"

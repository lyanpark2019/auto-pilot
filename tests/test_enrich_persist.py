"""Tests for scripts/_enrich_persist.py — gate-and-persist layer.

All candidate dicts are built with correctly-computed sha256 values via
canonical_sha() so the tests exercise the REAL evaluate() + persist() logic.
No mocking of the gate — Phase-2a acceptance requires end-to-end exercise.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Make scripts/ importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _enrich_gate import canonical_sha  # noqa: E402
from _enrich_persist import (  # noqa: E402
    enrichment_filename,
    persist,
    render_enrichment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _official(snippet: str = "Correct answer is 42.", **overrides: object) -> dict:
    """Build a minimal valid official-tier candidate."""
    base: dict = {
        "claim": "The answer",
        "source_tier": "official",
        "source_url": "https://docs.example.com/answer",
        "retrieved_date": "2026-06-14",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
    }
    base.update(overrides)
    return base


def _community_two_corr(
    snippet: str = "Community tip: frobnicate().",
    corr1_url: str = "https://forum.a.io/thread/1",
    corr2_url: str = "https://blog.b.com/posts/1",
) -> dict:
    """Build a valid community candidate with two independent corroborations."""
    corr1_snip = "Corroboration alpha."
    corr2_snip = "Corroboration beta."
    return {
        "claim": "Use frobnicate",
        "source_tier": "community",
        "source_url": "https://reddit.com/r/python/9999",
        "retrieved_date": "2026-06-14",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
        "corroborations": [
            {
                "source_url": corr1_url,
                "snippet": corr1_snip,
                "sha256": canonical_sha(corr1_snip),
            },
            {
                "source_url": corr2_url,
                "snippet": corr2_snip,
                "sha256": canonical_sha(corr2_snip),
            },
        ],
    }


def _community_single(snippet: str = "Community tip alone.") -> dict:
    """Community candidate with only one corroboration — should be REJECTed."""
    corr_snip = "Single corroboration."
    return {
        "claim": "Single source community",
        "source_tier": "community",
        "source_url": "https://reddit.com/r/python/0001",
        "retrieved_date": "2026-06-14",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
        "corroborations": [
            {
                "source_url": "https://forum.only.one/thread",
                "snippet": corr_snip,
                "sha256": canonical_sha(corr_snip),
            }
        ],
    }


# ---------------------------------------------------------------------------
# 1. ADMIT official candidate → exactly one page
# ---------------------------------------------------------------------------


def test_admit_official_creates_page(tmp_path: Path) -> None:
    snippet = "The real answer is 42."
    cand = _official(snippet=snippet, source_url="https://docs.lib.io/v2")
    counts = persist([cand], tmp_path)

    assert counts["admitted"] == 1
    assert counts["rejected"] == 0
    assert counts["written"] == 1
    assert counts["unchanged"] == 0

    expected_name = enrichment_filename(cand)
    page = tmp_path / "enrichment" / expected_name
    assert page.exists(), f"expected {page} to exist"

    text = page.read_text(encoding="utf-8")
    # Frontmatter fields
    assert f"sha256: {cand['sha256']}" in text
    assert "source_url: https://docs.lib.io/v2" in text
    assert "source_tier: official" in text
    assert "generator: _enrich_persist" in text
    # Snippet in body
    assert snippet in text


# ---------------------------------------------------------------------------
# 2. REJECT candidate → NO page written
# ---------------------------------------------------------------------------


def test_reject_community_single_no_page(tmp_path: Path) -> None:
    cand = _community_single()
    counts = persist([cand], tmp_path)

    assert counts["rejected"] >= 1
    assert counts["admitted"] == 0
    enrichment_dir = tmp_path / "enrichment"
    pages = list(enrichment_dir.glob("*.md")) if enrichment_dir.exists() else []
    assert pages == [], f"expected no pages, got {pages}"


def test_reject_sha_mismatch_no_page(tmp_path: Path) -> None:
    cand = _official(sha256="0" * 64)  # deliberate mismatch
    counts = persist([cand], tmp_path)

    assert counts["rejected"] >= 1
    enrichment_dir = tmp_path / "enrichment"
    pages = list(enrichment_dir.glob("*.md")) if enrichment_dir.exists() else []
    assert pages == []


# ---------------------------------------------------------------------------
# 3. Byte-stable re-run / UPSERT — second run: written=0, unchanged=1
# ---------------------------------------------------------------------------


def test_upsert_stable_second_run(tmp_path: Path) -> None:
    cand = _official(snippet="Upsert stability check.")
    # First run
    counts1 = persist([cand], tmp_path)
    assert counts1["written"] == 1
    assert counts1["unchanged"] == 0

    # Second run — byte-identical content → unchanged, not re-written
    counts2 = persist([cand], tmp_path)
    assert counts2["written"] == 0, "second run must not re-write identical content"
    assert counts2["unchanged"] == 1

    # Still exactly one page
    pages = list((tmp_path / "enrichment").glob("*.md"))
    assert len(pages) == 1


# ---------------------------------------------------------------------------
# 4. Mixed batch (1 admit + 1 reject)
# ---------------------------------------------------------------------------


def test_mixed_batch(tmp_path: Path) -> None:
    admit_cand = _official(snippet="Admissible fact.")
    reject_cand = _community_single(snippet="Single-source community tip.")

    counts = persist([admit_cand, reject_cand], tmp_path)

    assert counts["admitted"] == 1
    assert counts["rejected"] == 1
    pages = list((tmp_path / "enrichment").glob("*.md"))
    assert len(pages) == 1


# ---------------------------------------------------------------------------
# 5. Hand-authored non-owned page is never touched
# ---------------------------------------------------------------------------


def test_hand_authored_page_untouched(tmp_path: Path) -> None:
    enrichment_dir = tmp_path / "enrichment"
    enrichment_dir.mkdir()
    hand_page = enrichment_dir / "my-custom-note.md"
    hand_page.write_text("# Hand-authored note\nKeep me.\n", encoding="utf-8")
    original_mtime = hand_page.stat().st_mtime

    cand = _official(snippet="Will this touch hand page?")
    persist([cand], tmp_path)

    # Hand page content unchanged
    assert hand_page.read_text(encoding="utf-8") == "# Hand-authored note\nKeep me.\n"
    # mtime unchanged (no write occurred)
    assert hand_page.stat().st_mtime == original_mtime


# ---------------------------------------------------------------------------
# 6. Dry-run writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_no_disk_writes(tmp_path: Path) -> None:
    cand = _official(snippet="Dry-run fact, should not appear.")
    counts = persist([cand], tmp_path, dry_run=True)

    assert counts["admitted"] == 1
    assert counts["written"] == 1  # counted but not written
    enrichment_dir = tmp_path / "enrichment"
    pages = list(enrichment_dir.glob("*.md")) if enrichment_dir.exists() else []
    assert pages == [], "dry_run must not create any files"


# ---------------------------------------------------------------------------
# 7. CLI smoke — orchestrator.py enrich → rc 0, prints counts JSON
# ---------------------------------------------------------------------------


def test_cli_enrich_subcommand(tmp_path: Path) -> None:
    snippet = "CLI smoke test fact."
    cand = _official(snippet=snippet)

    candidate_file = tmp_path / "candidate.json"
    candidate_file.write_text(json.dumps(cand), encoding="utf-8")

    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "enrich",
            "--candidates",
            str(candidate_file),
            "--vault",
            str(tmp_path / "vault"),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )

    assert result.returncode == 0, f"CLI failed:\n{result.stderr}"
    output = json.loads(result.stdout.strip())
    assert output["admitted"] == 1
    assert output["written"] == 1
    assert output["rejected"] == 0


# ---------------------------------------------------------------------------
# 8. Community ADMIT (two independent corroborations) → page written
# ---------------------------------------------------------------------------


def test_community_two_corr_admitted(tmp_path: Path) -> None:
    cand = _community_two_corr()
    counts = persist([cand], tmp_path)

    assert counts["admitted"] == 1
    assert counts["rejected"] == 0
    pages = list((tmp_path / "enrichment").glob("*.md"))
    assert len(pages) == 1

    page_text = pages[0].read_text(encoding="utf-8")
    assert "source_tier: community" in page_text
    # Corroborations section rendered
    assert "## Corroborations" in page_text


# ---------------------------------------------------------------------------
# 9. render_enrichment — community page has Corroborations section
# ---------------------------------------------------------------------------


def test_render_enrichment_community_corr_section() -> None:
    cand = _community_two_corr(
        corr1_url="https://forum.a.io/t/1",
        corr2_url="https://blog.b.com/p/1",
    )
    page = render_enrichment(cand)
    assert "## Corroborations" in page
    assert "https://forum.a.io/t/1" in page
    assert "https://blog.b.com/p/1" in page
    assert "generator: _enrich_persist" in page
    assert "derived: true" in page


# ---------------------------------------------------------------------------
# 10. enrichment_filename is deterministic and dedup-keyed
# ---------------------------------------------------------------------------


def test_enrichment_filename_deterministic() -> None:
    snippet = "Same fact, different times."
    sha = canonical_sha(snippet)
    cand = _official(snippet=snippet, retrieved_date="2026-01-01")
    cand2 = _official(snippet=snippet, retrieved_date="2099-12-31")

    assert enrichment_filename(cand) == f"enrich-{sha}.md"
    assert enrichment_filename(cand) == enrichment_filename(cand2)


# ---------------------------------------------------------------------------
# 11. cmd_enrich error handling — bad --candidates path (Fix 2)
# ---------------------------------------------------------------------------


def test_cli_enrich_nonexistent_candidates_rc2(tmp_path: Path) -> None:
    """A nonexistent --candidates path must produce rc=2 with no traceback."""
    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "enrich",
            "--candidates",
            str(tmp_path / "does_not_exist.json"),
            "--vault",
            str(tmp_path / "vault"),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert result.returncode == 2, f"expected rc=2, got {result.returncode}"
    assert "Traceback" not in result.stderr, "must not produce a Python traceback"
    assert "error" in result.stderr.lower(), f"expected error message in stderr: {result.stderr!r}"


# ---------------------------------------------------------------------------
# 12. enrich-gate-reject emit — all-rejected triggers escalation record
# ---------------------------------------------------------------------------


def test_cmd_enrich_all_rejected_emits_escalation(tmp_path: Path) -> None:
    """cmd_enrich with all-rejected candidates emits an enrich-gate-reject escalation.

    Uses a single-source community candidate (REJECT) and an isolated repo-root
    so the escalation ledger is discoverable via escalation-list --repo-root.
    The emit is best-effort — rc and printed counts are unchanged.
    """
    from _enrich_gate import canonical_sha  # noqa: PLC0415

    # Build a community candidate that will be REJECTED (single corroboration).
    snippet = "enrich-gate-reject test snippet."
    cand = {
        "claim": "Test claim for rejection",
        "source_tier": "community",
        "source_url": "https://example.com/single",
        "retrieved_date": "2026-06-15",
        "snippet": snippet,
        "sha256": canonical_sha(snippet),
        "corroborations": [
            {
                "source_url": "https://only.one/corr",
                "snippet": "Only one corroboration.",
                "sha256": canonical_sha("Only one corroboration."),
            }
        ],
    }
    candidate_file = tmp_path / "reject_cand.json"
    candidate_file.write_text(json.dumps(cand), encoding="utf-8")

    repo_root = tmp_path / "isolated_repo"
    repo_root.mkdir()
    vault = tmp_path / "vault"

    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    # Override HOME to isolate the escalation ledger from the real home store.
    # Preserve PYTHONPATH so site-packages (jsonschema/referencing) remain reachable.
    import os  # noqa: PLC0415
    import site as _site  # noqa: PLC0415
    home_override = tmp_path / "fakehome"
    home_override.mkdir()
    # Preserve user site-packages explicitly so HOME override does not drop them.
    user_site = _site.getusersitepackages()
    existing_pp = os.environ.get("PYTHONPATH", "")
    pythonpath = os.pathsep.join(p for p in [existing_pp, user_site, str(scripts_dir)] if p)
    env = {
        **os.environ,
        "HOME": str(home_override),
        "PYTHONPATH": pythonpath,
    }
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "enrich",
            "--candidates", str(candidate_file),
            "--vault", str(vault),
            "--repo-root", str(repo_root),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
        env=env,
    )
    # rc and counts are unchanged
    assert result.returncode == 0, f"cmd_enrich failed:\n{result.stderr}"
    counts_out = json.loads(result.stdout.strip())
    assert counts_out["rejected"] == 1
    assert counts_out["admitted"] == 0

    # Verify escalation record was emitted via escalation-list
    r_list = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "escalation-list",
            "--json",
            "--repo-root", str(repo_root),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
        env=env,
    )
    assert r_list.returncode == 0, f"escalation-list failed:\n{r_list.stderr}"
    records = [json.loads(line) for line in r_list.stdout.strip().splitlines() if line.strip()]
    assert any(
        r.get("problem_class") == "enrich-gate-reject" for r in records
    ), f"expected enrich-gate-reject record, got {records}"


def test_cli_enrich_malformed_json_candidates_rc2(tmp_path: Path) -> None:
    """A malformed-JSON --candidates file must produce rc=2 with no traceback."""
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not valid json", encoding="utf-8")

    scripts_dir = Path(__file__).resolve().parent.parent / "scripts"
    result = subprocess.run(
        [
            sys.executable,
            str(scripts_dir / "orchestrator.py"),
            "enrich",
            "--candidates",
            str(bad_json),
            "--vault",
            str(tmp_path / "vault"),
        ],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert result.returncode == 2, f"expected rc=2, got {result.returncode}"
    assert "Traceback" not in result.stderr, "must not produce a Python traceback"
    assert "error" in result.stderr.lower(), f"expected error message in stderr: {result.stderr!r}"

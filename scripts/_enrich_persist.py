"""Gate-and-persist: admitted enrichment-evidence candidates → vault enrichment/ pages.

Phase-2a of inc2-enrich (deterministic slice; no network calls).
Candidates come from a file/dir; each is run through the Phase-1 gate
(_enrich_gate.evaluate) and ADMITted ones are persisted as vault
``enrichment/enrich-<sha256>.md`` pages.

Enrichment is ADDITIVE/UPSERT, not a mirror — pages are accumulated verified
knowledge keyed by content sha.  UPSERT by sha, NEVER prune.  A fact, once
verified and admitted, stays.

The ``enrich-<sha256>.md`` namespace is machine-owned — a hand-authored file
occupying that exact name is overwritten by design (sha-keyed, collision-resistant);
hand-authored enrichment notes must use a different filename.

CLI (via orchestrator.py):
    orchestrator.py enrich --candidates <path> [--vault <path>] [--dry-run]
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from _enrich_gate import evaluate
from _mirror_learnings import resolve_vault

GENERATOR = "_enrich_persist"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _yaml_scalar(s: str) -> str:
    """Strip newlines/CRs that would inject arbitrary YAML keys."""
    return str(s).replace("\r", " ").replace("\n", " ").strip()


def _atomic_write(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically via temp+rename (same dir)."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".md.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enrichment_filename(candidate: dict[str, Any]) -> str:
    """Return the deterministic filename for a candidate's enrichment page.

    The key is the candidate's own ``sha256`` field (sha256 of its snippet),
    so identical facts from the same or different sources produce one page.
    """
    return f"enrich-{candidate['sha256']}.md"


def render_enrichment(candidate: dict[str, Any]) -> str:
    """Render a deterministic markdown enrichment page for an ADMITted candidate.

    Uses only the candidate's own stable fields — no ``datetime.now()`` — so
    re-runs produce byte-identical output.
    """
    source_tier = _yaml_scalar(str(candidate.get("source_tier", "")))
    source_url = _yaml_scalar(str(candidate.get("source_url", "")))
    retrieved_date = _yaml_scalar(str(candidate.get("retrieved_date", "")))
    sha256 = _yaml_scalar(str(candidate.get("sha256", "")))

    claim_raw = str(candidate.get("claim", ""))
    claim_title = claim_raw[:80]

    snippet = str(candidate.get("snippet", ""))
    corroborations: list[dict[str, Any]] = candidate.get("corroborations") or []

    frontmatter = (
        "---\n"
        "type: enrichment\n"
        f"generator: {GENERATOR}\n"
        "derived: true\n"
        f"source_tier: {source_tier}\n"
        f"source_url: {source_url}\n"
        f"retrieved_date: {retrieved_date}\n"
        f"sha256: {sha256}\n"
        "---\n"
    )

    lines: list[str] = [
        f"# Enrichment — {claim_title}",
        "",
        "> Verified external knowledge (machine-persisted via `orchestrator.py enrich`"
        " — do not hand-edit). Admitted by the enrichment gate.",
        "",
        f"- **Claim:** {claim_raw}",
        f"- **Source tier:** {source_tier}",
        f"- **Source URL:** {source_url}",
        f"- **Retrieved date:** {retrieved_date}",
        "",
        "## Evidence",
        "",
        snippet,
    ]

    if corroborations:
        lines.append("")
        lines.append("## Corroborations")
        lines.append("")
        for corr in corroborations:
            corr_url = str(corr.get("source_url", ""))
            if corr_url:
                lines.append(f"- {corr_url}")

    body = "\n".join(lines) + "\n"

    return frontmatter + "\n" + body


def persist(
    candidates: list[dict[str, Any]],
    vault: Path,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Gate each candidate and persist ADMITted ones as vault enrichment/ pages.

    Returns counts: ``{"admitted": a, "rejected": r, "written": w, "unchanged": u}``
    where ``admitted == written + unchanged``.

    Enrichment is UPSERT-only — existing non-owned pages are never touched.
    When ``dry_run`` is True, counts are computed but no disk writes occur.
    """
    enrichment_dir = vault / "enrichment"

    admitted = 0
    rejected = 0
    written = 0
    unchanged = 0

    for candidate in candidates:
        verdict = evaluate(candidate)
        if verdict["verdict"] != "admit":
            rejected += 1
            continue

        admitted += 1
        filename = enrichment_filename(candidate)
        content = render_enrichment(candidate)
        dest = enrichment_dir / filename
        encoded = content.encode("utf-8")

        if dest.exists() and dest.read_bytes() == encoded:
            unchanged += 1
        else:
            if not dry_run:
                enrichment_dir.mkdir(parents=True, exist_ok=True)
                _atomic_write(dest, content)
            written += 1

    return {"admitted": admitted, "rejected": rejected, "written": written,
            "unchanged": unchanged}


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def register_cli_subparsers(sub: Any) -> None:
    """Register the ``enrich`` subcommand onto the orchestrator CLI parser."""
    p_en = sub.add_parser("enrich")
    p_en.add_argument(
        "--candidates",
        required=True,
        dest="candidates",
        help=(
            "Path to a JSON file (single candidate object or list) "
            "or a directory whose *.json files are each a candidate."
        ),
    )
    p_en.add_argument("--repo-root", default=".", dest="repo_root")
    p_en.add_argument(
        "--vault",
        default=None,
        dest="vault",
        help="Explicit vault path override (default: resolve_vault).",
    )
    p_en.add_argument("--dry-run", action="store_true", dest="dry_run")
    p_en.set_defaults(func=cmd_enrich)


def _load_candidates(path: Path) -> list[dict[str, Any]]:
    """Load candidates from a JSON file or a directory of JSON files."""
    if path.is_dir():
        result: list[dict[str, Any]] = []
        for p in sorted(path.glob("*.json")):
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                result.extend(data)
            else:
                result.append(data)
        return result

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return [data]


def cmd_enrich(args: Any) -> int:
    """CLI handler: gate and persist enrichment candidates into the vault."""
    candidates_path = Path(getattr(args, "candidates")).resolve()
    repo_root = Path(getattr(args, "repo_root", ".")).resolve()
    vault_arg = getattr(args, "vault", None)
    vault = Path(vault_arg) if vault_arg else resolve_vault(repo_root)
    dry_run = bool(getattr(args, "dry_run", False))

    try:
        candidates = _load_candidates(candidates_path)
    except (OSError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"error loading candidates from {candidates_path}: {exc}\n")
        return 2
    counts = persist(candidates, vault, dry_run=dry_run)
    print(json.dumps(counts))
    return 0

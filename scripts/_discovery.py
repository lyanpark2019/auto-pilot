"""Deterministic graphify-context discovery seam (master-plan §5 Step 1).

Python never snapshots the graph — graphify's LLM semantic layer is
non-reproducible, so the graph is recorded only by provenance (build commit +
graphify version + timestamp). Freshness is diff-relevance, NOT sha-equality:
a recorded context stays fresh while no commit since ``build_commit`` touches
the next phase's scope files. Plain commit inequality would force a regen
after every phase merge and defeat the seam entirely.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

PROVENANCE_FILE = "graphify-provenance.json"
DEFAULT_REPORT_RELPATH = Path("graphify-out/GRAPH_REPORT.md")
_GIT_TIMEOUT = 30


@dataclass(frozen=True)
class Freshness:
    """Verdict for one ``check_freshness`` call."""

    fresh: bool
    reason: str
    changed_files: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serializable dict (CLI output shape)."""
        return {
            "fresh": self.fresh,
            "reason": self.reason,
            "changed_files": list(self.changed_files),
        }


def _git_head(repo_root: Path) -> str:
    """Current HEAD sha, or "" when HEAD is unresolvable (unborn / non-git).

    Fail-soft like ``_changed_since`` — never raise, so the freshness check
    cannot block dispatch on a missing or unborn git context.
    """
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=_GIT_TIMEOUT,
        )
    except OSError:
        return ""
    if res.returncode != 0:
        return ""
    return res.stdout.strip()


def record_provenance(
    *, repo_root: Path, state_dir: Path, graphify_version: str
) -> dict[str, str]:
    """Write provenance for a graphify run the PM just completed.

    Called AFTER the PM ran graphify — this module never runs graphify itself.

    Returns:
        The payload written to ``state_dir/PROVENANCE_FILE``.
    """
    payload = {
        "build_commit": _git_head(repo_root),
        "graphify_version": graphify_version,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(state_dir), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, state_dir / PROVENANCE_FILE)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return payload


def _load_provenance(state_dir: Path) -> dict[str, Any] | None:
    path = state_dir / PROVENANCE_FILE
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _changed_since(repo_root: Path, build_commit: str) -> tuple[str, ...] | None:
    """Files changed ``build_commit..HEAD``; None when the commit is unknown."""
    res = subprocess.run(
        ["git", "-C", str(repo_root), "diff", "--name-only", f"{build_commit}..HEAD"],
        capture_output=True, text=True, timeout=_GIT_TIMEOUT,
    )
    if res.returncode != 0:
        return None
    return tuple(line for line in res.stdout.splitlines() if line.strip())


def _scope_hits(changed: tuple[str, ...], scope_files: Sequence[str]) -> tuple[str, ...]:
    hits: list[str] = []
    for path in changed:
        for scope in scope_files:
            if path == scope or (scope.endswith("/") and path.startswith(scope)):
                hits.append(path)
                break
    return tuple(hits)


def check_freshness(
    *,
    repo_root: Path,
    state_dir: Path,
    graphify_version: str,
    scope_files: Sequence[str] = (),
) -> Freshness:
    """Pure-git freshness verdict for the recorded graphify context.

    Stale reasons: ``never-recorded``, ``provenance-corrupt``,
    ``version-changed``, ``head-unresolvable`` (unborn / non-git — fail soft,
    never block), ``build-commit-unknown``, ``scope-intersects``,
    ``changed-no-scope`` (conservative — caller gave no scope, commits differ).
    Fresh reasons: ``same-commit``, ``no-scope-overlap``.

    Compares committed history only (HEAD); uncommitted working-tree edits are
    invisible here — the loop merges each phase before the next check.
    """
    prov = _load_provenance(state_dir)
    if prov is None:
        return Freshness(fresh=False, reason="never-recorded")
    if not prov or not isinstance(prov.get("build_commit"), str):
        return Freshness(fresh=False, reason="provenance-corrupt")
    if prov.get("graphify_version") != graphify_version:
        return Freshness(fresh=False, reason="version-changed")

    build_commit: str = prov["build_commit"]
    head = _git_head(repo_root)
    if not head:
        return Freshness(fresh=False, reason="head-unresolvable")
    if build_commit == head:
        return Freshness(fresh=True, reason="same-commit")

    changed = _changed_since(repo_root, build_commit)
    if changed is None:
        return Freshness(fresh=False, reason="build-commit-unknown")
    if not scope_files:
        return Freshness(fresh=False, reason="changed-no-scope", changed_files=changed)
    hits = _scope_hits(changed, scope_files)
    if hits:
        return Freshness(fresh=False, reason="scope-intersects", changed_files=hits)
    return Freshness(fresh=True, reason="no-scope-overlap")


def resolve_report(
    *,
    repo_root: Path,
    state_dir: Path,
    graphify_version: str,
    scope_files: Sequence[str] = (),
    report_relpath: Path = DEFAULT_REPORT_RELPATH,
) -> tuple[Path | None, Freshness]:
    """Resolve the graphify report to bundle as ``project-context.md``, or None.

    The path is non-None only when the report file exists AND provenance is
    fresh for the given scope. On a None verdict the PM regenerates graphify,
    calls :func:`record_provenance`, and resolves again; if still None it
    proceeds context-blind (``verify_snapshots`` logs that downstream).
    """
    report = repo_root / report_relpath
    if not report.exists():
        return None, Freshness(fresh=False, reason="report-missing")
    verdict = check_freshness(
        repo_root=repo_root, state_dir=state_dir,
        graphify_version=graphify_version, scope_files=scope_files,
    )
    if not verdict.fresh:
        return None, verdict
    return report, verdict

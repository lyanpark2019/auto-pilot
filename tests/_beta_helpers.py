from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "contracts" / "sample_contract.json"


def _make_contract_dir(tmp_path: Path) -> Path:
    import _contract
    contract = json.loads(FIXTURE.read_text())
    dest = tmp_path / "contracts" / "iter-1/phase-1/contract-1/round-1"
    dest.mkdir(parents=True)
    bundle = dest / "context-bundle"
    bundle.mkdir()
    (bundle / "spec.md").write_text("# spec\n")
    (bundle / "MANIFEST.txt").write_text(_contract._sha256(b"# spec\n") + "  spec.md\n")
    contract["context_bundle_path"] = str(bundle)
    contract["snapshot_shas"]["spec"] = _contract._sha256(b"# spec\n")
    contract["snapshot_shas"]["claude_md_chain"] = []
    _contract.write_contract(contract, dest / "contract.json")
    _contract.write_pm_signature(dest, run_id="run-test")
    return dest


def _write_contract_check(contract_dir: Path) -> None:
    """Write a valid contract-check.json beside the contract file."""
    import hashlib
    contract_path = contract_dir / "contract.json"
    sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    schema_v = json.loads(contract_path.read_text()).get("schema_version", 2)
    artifact = {
        "contract_sha256": sha,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": schema_v,
        "result": "pass",
    }
    (contract_dir / "contract-check.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    )


def _write_preflight(repo_root: Path, phase: int, *,
                     head_sha: str | None = None,
                     generated_ts: str | None = None) -> Path:
    """Write a valid preflight artifact for the given phase."""
    if head_sha is None:
        try:
            head_sha = subprocess.check_output(
                ["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True
            ).strip()
        except subprocess.CalledProcessError:
            head_sha = "a" * 40
    if generated_ts is None:
        generated_ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    preflight_dir = repo_root / ".planning" / "auto-pilot" / "preflight"
    preflight_dir.mkdir(parents=True, exist_ok=True)
    artifact = {
        "repo_root": str(repo_root),
        "branch": "feat/test",
        "head_sha": head_sha,
        "worktree_clean": True,
        "expected_gh_user": "Sewhoan",
        "actual_gh_user": "Sewhoan",
        "tool_versions": {"python3": "3.13.0", "git": "2.45.0", "codex": None, "claude": None},
        "generated_ts": generated_ts,
        "phase": phase,
    }
    path = preflight_dir / f"phase-{phase}.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return path

"""Phase 6 — Per-domain vault-builder execution.

Two modes:
  1. Manifest mode (default): emit build manifest, score existing state.
  2. Execute mode (`ctx.execute_builds=True`): shell out to `claude -p "/vault-build ..."`
     per pending domain, autonomously running each PM loop until pass or max rounds.

Execute mode requires `claude` CLI in PATH (v2.1.141+) and authenticated session.
Each domain dispatch is bounded by `--max-budget-usd` to prevent runaway cost.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from ._base import Phase, PhaseResult
from ._mapping import DOMAINS, PASS_THRESHOLD, MAX_VAULT_BUILD_ROUNDS

# Primary pattern: "Score: 97.2/100", "**Score:** 97.2/100", "structural score: 71/100"
_SCORE_PAT = re.compile(
    r"(?:structural\s+)?score\b[^\d]{0,12}(\d+(?:\.\d+)?)\s*/\s*100",
    re.IGNORECASE,
)
# Fallback: "39.6-pt gap" / "Remaining gap (1.3 pt)" / "1.3 pt gap" → 100 - X
_GAP_PAT = re.compile(
    r"(?:remaining\s+)?(?:gap\s*\(?\s*)?(\d+(?:\.\d+)?)\s*[-\s]?\s*pt\s*\)?\s*gap",
    re.IGNORECASE,
)
_GAP_PAT_REV = re.compile(
    r"gap\s*\(?\s*(\d+(?:\.\d+)?)\s*[-\s]?\s*pt\b",
    re.IGNORECASE,
)

PER_DOMAIN_BUDGET_USD = float(os.environ.get("VAULT_BUILD_BUDGET_USD", "0"))  # 0 = no cap (subscription mode)
PER_DOMAIN_TIMEOUT_SEC = int(os.environ.get("VAULT_BUILD_TIMEOUT_SEC", "1800"))  # 30 min


class VaultBuildPerDomainPhase(Phase):
    name = "6_vault_build_per_domain"
    deps = ["5_new_vault_skeletons"]

    def _build_manifest(self) -> list[dict]:
        """One entry per (domain × sub-project).

        Vault structure target:  <domain-Vault>/_sub-projects/<sub-name>/...
        vault-build invocation:  /vault-build <repo> --obsidian-path <vault>/_sub-projects --project-name <sub-name>
        """
        out = []
        for domain, info in DOMAINS.items():
            vault = self.ctx.obsidian_root / info["vault"]
            sub_root = vault / "_sub-projects"
            for sub_path in info["sub_projects"]:
                repo = self.ctx.project_root / sub_path
                sub_name = Path(sub_path).name  # e.g. lyan/PickL → PickL
                cmd = f"/vault-build {repo} --obsidian-path {sub_root} --project-name {sub_name}"
                out.append(
                    {
                        "domain": domain,
                        "sub_project": sub_path,
                        "sub_name": sub_name,
                        "key": f"{domain}::{sub_name}",
                        "vault": str(vault),
                        "sub_root": str(sub_root),
                        "input_repo": str(repo),
                        "input_repo_exists": repo.is_dir(),
                        "vault_exists": vault.is_dir(),
                        "command": cmd,
                    }
                )
        return out

    def dry_run(self) -> str:
        manifest = self._build_manifest()
        out = [f"[Phase 6] Per-sub-project vault-build manifest ({len(manifest)} entries):"]
        for entry in manifest:
            mark = "✓" if entry["input_repo_exists"] and entry["vault_exists"] else "?"
            out.append(f"  {mark} {entry['key']:36s} {entry['command']}")
        out.append(f"  pass threshold: {PASS_THRESHOLD}, max rounds: {MAX_VAULT_BUILD_ROUNDS}")
        if getattr(self.ctx, "execute_builds", False):
            out.append("  EXECUTE MODE: will shell out to `claude -p` per pending entry")
        else:
            out.append("  manifest mode (no execution); pass --execute-builds to actually run")
        return "\n".join(out)

    def _score_vault(self, vault: Path) -> int | None:
        """Run NotebookLM-style scorer; returns total from meta/score-state.json."""
        try:
            subprocess.run(
                [sys.executable, str(self.ctx.plugin_root / "scripts" / "score_structural.py"), str(vault)],
                capture_output=True, text=True, timeout=60,
            )
            state = vault / "meta" / "score-state.json"
            if not state.exists():
                return None
            data = json.loads(state.read_text())
            return int(round(float(data.get("total", 0))))
        except Exception as exc:
            print(f"phase06: _score_vault failed for {vault}: {type(exc).__name__}: {exc}", file=sys.stderr)
            return None

    def _score_from_verify_report(self, project_path: Path) -> int | None:
        """Read canonical score from <project>/.vault-builder/verify-report.md."""
        report = project_path / ".vault-builder" / "verify-report.md"
        if not report.exists():
            return None
        try:
            text = report.read_text()
            m = _SCORE_PAT.search(text)
            if m:
                return int(round(float(m.group(1))))
        except Exception as exc:
            print(f"phase06: _score_from_verify_report failed for {report}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None

    def _score_from_stdout(self, stdout_tail: str) -> int | None:
        """Extract final score from vault-build stdout.

        Accepts multiple phrasings:
          - "Score: NN.N/100"            → NN.N
          - "**Final structural score: NN.N/100**"
          - "39.6-pt gap" / "Remaining gap (1.3 pt)" → 100 - 39.6 / 100 - 1.3
        """
        if not stdout_tail:
            return None
        m = _SCORE_PAT.search(stdout_tail)
        if m:
            try:
                return int(round(float(m.group(1))))
            except (TypeError, ValueError) as exc:
                print(f"phase06: failed to convert score match '{m.group(1)}': {type(exc).__name__}: {exc}", file=sys.stderr)
        for pat in (_GAP_PAT, _GAP_PAT_REV):
            m = pat.search(stdout_tail)
            if m:
                try:
                    gap = float(m.group(1))
                    return int(round(100 - gap))
                except (TypeError, ValueError) as exc:
                    print(f"phase06: failed to convert gap match '{m.group(1)}': {type(exc).__name__}: {exc}", file=sys.stderr)
        return None

    def _execute_one(self, claude_bin: str, entry: dict) -> dict:
        """Dispatch /vault-build for this domain via headless claude.

        Use natural-language prompt because `claude -p '/literal-cmd'` treats slash
        commands as unknown native commands; phrasing it as a directive lets the
        plugin's command (resolved via --plugin-dir) be invoked through the Agent.
        """
        prompt = (
            f"Run the vault-builder plugin's /vault-build command to document a project.\n\n"
            f"Project path: {entry['input_repo']}\n"
            f"Obsidian vault target: {entry['vault']}\n"
            f"Project name: {Path(entry['vault']).name}\n\n"
            f"Equivalent slash invocation: {entry['command']}\n\n"
            f"Drive the full pipeline (scan → drift → fix via PM-Worker-Ticket loop "
            f"→ verify against rubric → export to Obsidian) until completion. "
            f"After it finishes, report the final structural score (NN/100), round count, "
            f"and per-dim breakdown."
        )
        cmd = [
            claude_bin,
            "-p", prompt,
            "--plugin-dir", str(self.ctx.plugin_root),
            "--dangerously-skip-permissions",
            "--output-format", "text",
        ]
        # --max-budget-usd only works with API-key billing. For subscription mode,
        # omit the flag entirely (plan quota governs).
        if PER_DOMAIN_BUDGET_USD > 0:
            cmd.extend(["--max-budget-usd", str(PER_DOMAIN_BUDGET_USD)])
            self.ctx.trace(f"  exec: claude -p (vault-build {entry['key']}) --max-budget {PER_DOMAIN_BUDGET_USD}")
        else:
            self.ctx.trace(f"  exec: claude -p (vault-build {entry['key']}) [subscription mode]")
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=PER_DOMAIN_TIMEOUT_SEC)
            return {
                "rc": r.returncode,
                "stdout_tail": r.stdout[-1200:] if r.stdout else "",
                "stderr_tail": r.stderr[-400:] if r.stderr else "",
            }
        except subprocess.TimeoutExpired:
            return {"rc": -1, "stdout_tail": "", "stderr_tail": f"timeout after {PER_DOMAIN_TIMEOUT_SEC}s"}

    def run(self) -> PhaseResult:
        manifest = self._build_manifest()
        manifest_path = self.ctx.state_path.parent / "obsidian-restructure-build-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        self.ctx.trace(f"  build manifest → {manifest_path}")

        # Load prior entry_state from state file so completed/partial entries persist
        # across runs (idempotency). New entries get pending; missing entries unchanged.
        prior_state = {}
        try:
            prior = json.loads(self.ctx.state_path.read_text())
            prior_state = prior.get("phases", {}).get("6_vault_build_per_domain", {}).get("entries", {}) or {}
        except Exception as exc:
            print(f"phase06: failed to load prior state from {self.ctx.state_path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            prior_state = {}

        entry_state: dict[str, dict] = {}
        for entry in manifest:
            key = entry["key"]
            existing = prior_state.get(key, {})
            entry_state[key] = {
                "domain": entry["domain"],
                "sub_project": entry["sub_project"],
                "score_before": existing.get("score_before"),
                "score": existing.get("score"),
                "score_source": existing.get("score_source"),
                "status": existing.get("status", "pending" if entry["input_repo_exists"] else "skipped"),
                "rounds": existing.get("rounds", 0),
                "max_rounds": MAX_VAULT_BUILD_ROUNDS,
                "command": entry["command"],
                "input_repo_exists": entry["input_repo_exists"],
                "skip_reason": None if entry["input_repo_exists"] else "input_repo missing",
                "last_exec": existing.get("last_exec"),
            }

        # Execute mode
        if getattr(self.ctx, "execute_builds", False):
            claude_bin = shutil.which("claude")
            if not claude_bin:
                self.ctx.trace("  ! claude CLI not on PATH; cannot execute. Manifest emitted only.")
            else:
                pending = [e for e in manifest if entry_state[e["key"]]["status"] == "pending"]
                only = getattr(self.ctx, "only_domain", None)
                if only:
                    allowed = {s.strip() for s in only.split(",") if s.strip()}
                    pending = [e for e in pending if e["domain"] in allowed]
                    self.ctx.trace(f"  filter: only_domain={sorted(allowed)}")
                self.ctx.trace(f"  {len(pending)} pending entry(ies) to dispatch via headless claude")
                for entry in pending:
                    key = entry["key"]
                    result = self._execute_one(claude_bin, entry)
                    entry_state[key]["last_exec"] = result
                    # Canonical score source: verify-report.md (written by vault-build Phase 4).
                    # Fallbacks: parse stdout (regex) → None.
                    project = Path(entry["input_repo"])
                    score = self._score_from_verify_report(project)
                    source = "verify-report.md"
                    if score is None:
                        score = self._score_from_stdout(result.get("stdout_tail", ""))
                        source = "vault-build stdout" if score is not None else "unknown"
                    entry_state[key]["score"] = score
                    entry_state[key]["score_source"] = source
                    entry_state[key]["rounds"] += 1
                    if score is not None and score >= PASS_THRESHOLD:
                        entry_state[key]["status"] = "completed"
                    elif result["rc"] != 0:
                        entry_state[key]["status"] = "failed"
                    else:
                        entry_state[key]["status"] = "partial"
                    self.ctx.trace(f"  {key:36s} score={score} ({source}) rc={result['rc']} → {entry_state[key]['status']}")

        completed = sum(1 for d in entry_state.values() if d["status"] == "completed")
        skipped = sum(1 for d in entry_state.values() if d["status"] == "skipped")
        total = len(entry_state)
        overall = "completed" if completed == (total - skipped) else "partial"
        return PhaseResult(
            status=overall,
            detail=f"{completed}/{total - skipped} sub-projects pass (skipped {skipped})",
            artifacts={"entries": entry_state, "manifest": str(manifest_path)},
        )

    def verify(self) -> tuple[bool, str]:
        manifest_path = self.ctx.state_path.parent / "obsidian-restructure-build-manifest.json"
        if not manifest_path.exists():
            return False, "build manifest missing"
        return True, "manifest emitted"

    def rollback(self) -> None:
        return

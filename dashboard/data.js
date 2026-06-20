window.DASHBOARD_DATA = {
 "branch": "chore/remove-dead-features",
 "commit": "6dba841",
 "counts": {
  "skill": 7,
  "agent": 15,
  "command": 7,
  "hook": 26,
  "codex-skill": 11
 },
 "assets": [
  {
   "type": "skill",
   "name": "adversarial-review-loop",
   "subsystem": "quality"
  },
  {
   "type": "skill",
   "name": "auto-pilot",
   "subsystem": "core-loop"
  },
  {
   "type": "skill",
   "name": "doc-management",
   "subsystem": "docs-core"
  },
  {
   "type": "skill",
   "name": "quality-eval",
   "subsystem": "quality"
  },
  {
   "type": "skill",
   "name": "residue-audit",
   "subsystem": "quality"
  },
  {
   "type": "skill",
   "name": "setup-harness",
   "subsystem": "harness"
  },
  {
   "type": "skill",
   "name": "sha-deploy-standard",
   "subsystem": "deploy"
  },
  {
   "type": "agent",
   "name": "auto-pilot-claude-reviewer",
   "subsystem": "core-loop"
  },
  {
   "type": "agent",
   "name": "auto-pilot-codex-reviewer",
   "subsystem": "core-loop"
  },
  {
   "type": "agent",
   "name": "enrichment-fetcher",
   "subsystem": "other"
  },
  {
   "type": "agent",
   "name": "escalation-resolver",
   "subsystem": "other"
  },
  {
   "type": "agent",
   "name": "pm-orchestrator",
   "subsystem": "core-loop"
  },
  {
   "type": "agent",
   "name": "retro",
   "subsystem": "core-loop"
  },
  {
   "type": "agent",
   "name": "review-gatekeeper",
   "subsystem": "review"
  },
  {
   "type": "agent",
   "name": "specialist-pool",
   "subsystem": "review"
  },
  {
   "type": "agent",
   "name": "tech-critic-lead",
   "subsystem": "review"
  },
  {
   "type": "agent",
   "name": "vault-edge-curator",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "agent",
   "name": "vault-graph-enricher",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "agent",
   "name": "vault-knowledge-author",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "agent",
   "name": "vault-pm-orchestrator",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "agent",
   "name": "vault-structure-curator",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "agent",
   "name": "worker",
   "subsystem": "core-loop"
  },
  {
   "type": "command",
   "name": "auto-pilot-server",
   "subsystem": "core-loop"
  },
  {
   "type": "command",
   "name": "setup-claude-md",
   "subsystem": "harness"
  },
  {
   "type": "command",
   "name": "sha-deploy-init",
   "subsystem": "deploy"
  },
  {
   "type": "command",
   "name": "vault-build",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "command",
   "name": "vault-dashboard",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "command",
   "name": "vault-score",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "command",
   "name": "vault-selftest",
   "subsystem": "docs-vault-export"
  },
  {
   "type": "hook",
   "name": "_stdin_contract.py",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "artifact-ledger.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "branch-lock.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "context-watch.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "creation-gate.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "deletion-diff-guard.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "dispatch-contract-gate.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "doc-sync-update.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "gh-auth-preflight.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "guard-destructive.py",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "headless-sync-dispatch-guard.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "notebooklm_delete_gate.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "pm_final_report.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "post-deploy-verify.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "pre-bash-guard.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "pre-edit-composition-root.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "pre-edit-human-only.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "pre-reviewer-write.sh",
   "subsystem": "review"
  },
  {
   "type": "hook",
   "name": "preflight-path.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "ruff-import-integrity.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "session-distill-stop.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "shellcheck-on-write.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "state-write-guard.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "subagent-deliverable-check.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "verifier-tier-gate.sh",
   "subsystem": "other"
  },
  {
   "type": "hook",
   "name": "worker-scope-gate.sh",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "diagnose",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "grill-with-docs",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "handoff",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "improve-codebase-architecture",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "migrate-to-codex",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "prototype",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "tdd",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "to-issues",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "to-prd",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "triage",
   "subsystem": "other"
  },
  {
   "type": "codex-skill",
   "name": "zoom-out",
   "subsystem": "other"
  }
 ],
 "rounds": []
};

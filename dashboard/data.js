window.DASHBOARD_DATA = {
 "branch": "main",
 "commit": "1664e87",
 "counts": {
  "skill": 11,
  "agent": 16,
  "command": 7,
  "hook": 26,
  "codex-skill": 12
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
   "name": "codex-orchestra",
   "subsystem": "conductor"
  },
  {
   "type": "skill",
   "name": "diagnosing",
   "subsystem": "diagnostics"
  },
  {
   "type": "skill",
   "name": "doc-management",
   "subsystem": "docs-core"
  },
  {
   "type": "skill",
   "name": "improve-codebase-architecture",
   "subsystem": "diagnostics"
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
   "type": "skill",
   "name": "swarm",
   "subsystem": "swarm"
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
   "name": "swarm-explorer",
   "subsystem": "swarm"
  },
  {
   "type": "agent",
   "name": "swarm-monitor",
   "subsystem": "swarm"
  },
  {
   "type": "agent",
   "name": "swarm-verifier",
   "subsystem": "swarm"
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
   "name": "codex-conductor-guard.py",
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
   "name": "learning-miner-stop.sh",
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
   "name": "codex-orchestra",
   "subsystem": "conductor"
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
   "subsystem": "diagnostics"
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
 "rounds": [
  {
   "round": 0,
   "label": "provisional (analysis-based, pre-loop)",
   "generated": "2026-06-06",
   "assets": {
    "skill:doc-management": {
     "core_fit": 10,
     "uniqueness": 9,
     "evidence": 8,
     "cost": 7,
     "verdict": "CORE",
     "note": "단일 진입점 3모드 (REBUILD/MAINTAIN/AUDIT) — graphify doc 시스템 본체",
     "total": 8.9
    },
    "skill:graphify-doc-rebuild": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ doc-management REBUILD 모드 후 파일 삭제",
     "total": 8.4
    },
    "skill:doc-drift-audit": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 7,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "→ AUDIT 모드 흡수 후 삭제; claim-ledger 비채택",
     "total": 6.1
    },
    "skill:doc-sync": {
     "core_fit": 5,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "중간산출 → MAINTAIN 모드 흡수 후 삭제",
     "total": 4.8
    },
    "skill:llm-wiki-architect": {
     "core_fit": 1,
     "uniqueness": 1,
     "evidence": 2,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "per-module wiki = rot machine",
     "total": 1.9
    },
    "skill:auto-pilot": {
     "core_fit": 10,
     "uniqueness": 9,
     "evidence": 9,
     "cost": 6,
     "verdict": "CORE",
     "note": "자율 루프 본체, 228 tests",
     "total": 9.0
    },
    "skill:adversarial-review-loop": {
     "core_fit": 10,
     "uniqueness": 9,
     "evidence": 9,
     "cost": 6,
     "verdict": "CORE",
     "note": "리뷰 엔진 3모드",
     "total": 9.0
    },
    "skill:quality-eval": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 7,
     "verdict": "CORE",
     "note": "13-dim rubric SoT",
     "total": 8.2
    },
    "skill:pm-quality-harness-loop": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "superset orchestrator — 명시적 compose",
     "total": 7.5
    },
    "skill:residue-audit": {
     "core_fit": 8,
     "uniqueness": 9,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "semantic dead-code — linter 보완 유일",
     "total": 7.7
    },
    "skill-shell:codebase-perfection-loop": {
     "core_fit": 2,
     "uniqueness": 3,
     "evidence": 6,
     "cost": 8,
     "verdict": "REMOVE",
     "note": "DEPRECATED — references/ 만 보존",
     "total": 4.0
    },
    "skill:setup-harness": {
     "core_fit": 9,
     "uniqueness": 9,
     "evidence": 8,
     "cost": 5,
     "verdict": "CORE",
     "note": "하네스 부트스트랩 8-step",
     "total": 8.2
    },
    "skill:codex-orchestra": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "conductor 모드 + guard 페어",
     "total": 7.8
    },
    "skill:autopilot-swarm": {
     "core_fit": 8,
     "uniqueness": 9,
     "evidence": 6,
     "cost": 5,
     "verdict": "INTEGRATE",
     "note": "→ swarm 개명 + init/status/stop/ticket 통합",
     "total": 7.4
    },
    "skill:swarm-init": {
     "core_fit": 4,
     "uniqueness": 3,
     "evidence": 5,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ swarm 통합",
     "total": 4.5
    },
    "skill:swarm-status": {
     "core_fit": 4,
     "uniqueness": 3,
     "evidence": 5,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ swarm 통합",
     "total": 4.5
    },
    "skill:swarm-stop": {
     "core_fit": 4,
     "uniqueness": 3,
     "evidence": 5,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ swarm 통합",
     "total": 4.5
    },
    "skill:swarm-ticket": {
     "core_fit": 4,
     "uniqueness": 3,
     "evidence": 5,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ swarm 통합",
     "total": 4.5
    },
    "skill:swarm-bench": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "3-way 벤치 — 별기능",
     "total": 7.1
    },
    "skill:sha-deploy-standard": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 5,
     "cost": 8,
     "verdict": "KEEP",
     "note": "SHA-pin CI/CD 패턴",
     "total": 7.0
    },
    "skill:diagnosing-llm-output-leaks": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 5,
     "cost": 9,
     "verdict": "KEEP",
     "note": "진단 전용",
     "total": 7.2
    },
    "skill:diagnosing-stale-runtime": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 5,
     "cost": 9,
     "verdict": "KEEP",
     "note": "진단 전용",
     "total": 7.2
    },
    "skill:improve-codebase-architecture": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "deep-module 발견",
     "total": 7.6
    },
    "command:auto-pilot": {
     "core_fit": 8,
     "uniqueness": 7,
     "evidence": 8,
     "cost": 9,
     "verdict": "CORE",
     "note": "preflight 체크",
     "total": 7.9
    },
    "command:auto-pilot-server": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "headless driver",
     "total": 7.8
    },
    "command:eval-run": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "Nisi evals 계층",
     "total": 7.8
    },
    "command:quality-loop": {
     "core_fit": 2,
     "uniqueness": 1,
     "evidence": 6,
     "cost": 9,
     "verdict": "REMOVE",
     "note": "순수 alias — 스킬 트리거 커버",
     "total": 3.6
    },
    "command:setup-claude-md": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "prohibition-mining 고유",
     "total": 7.2
    },
    "command:harness-plan": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness plan",
     "total": 6.1
    },
    "command:harness-build": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness build",
     "total": 6.1
    },
    "command:harness-qa": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness qa",
     "total": 6.1
    },
    "command:harness-setup": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops setup",
     "total": 6.1
    },
    "command:harness-drift": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops drift",
     "total": 6.1
    },
    "command:harness-loop": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops loop",
     "total": 6.1
    },
    "command:harness-score": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops score",
     "total": 6.1
    },
    "command:harness-verify": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops verify",
     "total": 6.1
    },
    "command:vault-build": {
     "core_fit": 6,
     "uniqueness": 7,
     "evidence": 4,
     "cost": 6,
     "verdict": "KEEP",
     "note": "export 진입 (doc-purpose retired)",
     "total": 5.8
    },
    "command:vault-drift": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 3,
     "cost": 7,
     "verdict": "REMOVE",
     "note": "MAINTAIN/AUDIT 이 대체",
     "total": 3.0
    },
    "command:vault-audit": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "→ vault-score 모드",
     "total": 3.6
    },
    "command:vault-content-verify": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "→ vault-score 모드",
     "total": 3.6
    },
    "command:vault-score": {
     "core_fit": 5,
     "uniqueness": 5,
     "evidence": 4,
     "cost": 7,
     "verdict": "KEEP",
     "note": "score+audit+verify 통합 본체",
     "total": 5.1
    },
    "command:vault-restructure": {
     "core_fit": 4,
     "uniqueness": 5,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-build flag",
     "total": 4.3
    },
    "command:vault-resume": {
     "core_fit": 4,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ vault-build flag",
     "total": 4.4
    },
    "command:vault-dashboard": {
     "core_fit": 6,
     "uniqueness": 7,
     "evidence": 4,
     "cost": 8,
     "verdict": "KEEP",
     "note": "대시보드 패턴 원조",
     "total": 6.2
    },
    "command:vault-selftest": {
     "core_fit": 7,
     "uniqueness": 6,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "플러그인 자가검증",
     "total": 6.7
    },
    "command:nbm-to-obsidian": {
     "core_fit": 2,
     "uniqueness": 1,
     "evidence": 3,
     "cost": 9,
     "verdict": "REMOVE",
     "note": "자칭 legacy alias",
     "total": 3.0
    },
    "command:sha-deploy-init": {
     "core_fit": 7,
     "uniqueness": 7,
     "evidence": 5,
     "cost": 8,
     "verdict": "KEEP",
     "note": "ci.yml 생성",
     "total": 6.8
    },
    "agent:pm-orchestrator": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 7,
     "verdict": "CORE",
     "note": "루프 PM 계약",
     "total": 8.2
    },
    "agent:worker": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "scope-bound 구현",
     "total": 8.4
    },
    "agent:retro": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 5,
     "cost": 8,
     "verdict": "CORE",
     "note": "Nisi 회고→메모리 (신규)",
     "total": 7.4
    },
    "agent:claude-reviewer": {
     "core_fit": 7,
     "uniqueness": 6,
     "evidence": 8,
     "cost": 8,
     "verdict": "KEEP",
     "note": "legacy shell — review-core 인용",
     "total": 7.1
    },
    "agent:codex-adversarial": {
     "core_fit": 7,
     "uniqueness": 6,
     "evidence": 8,
     "cost": 8,
     "verdict": "KEEP",
     "note": "legacy shell — review-core 인용",
     "total": 7.1
    },
    "agent:auto-pilot-claude-reviewer": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "ticket+sandbox 강화판",
     "total": 8.4
    },
    "agent:auto-pilot-codex-reviewer": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "diff SHA 검증판",
     "total": 8.4
    },
    "agent:tdd-enforcer": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "test-first 게이트",
     "total": 7.8
    },
    "agent:security-reviewer": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "OWASP 게이트",
     "total": 7.8
    },
    "agent:tech-critic-lead": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "CTO pre-gate",
     "total": 7.8
    },
    "agent:specialist-pool": {
     "core_fit": 6,
     "uniqueness": 6,
     "evidence": 5,
     "cost": 9,
     "verdict": "KEEP",
     "note": "레지스트리 (비실행)",
     "total": 6.2
    },
    "agent:code-perfector": {
     "core_fit": 6,
     "uniqueness": 6,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "올인원 정리 파이프라인",
     "total": 6.2
    },
    "agent:harness-planner": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "3-agent harness ①",
     "total": 7.8
    },
    "agent:harness-generator": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "② PickL fork upstream 됨",
     "total": 7.8
    },
    "agent:harness-evaluator": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "③ 강화 vetting",
     "total": 7.8
    },
    "agent:goal-judge": {
     "core_fit": 5,
     "uniqueness": 6,
     "evidence": 5,
     "cost": 8,
     "verdict": "REMOVE",
     "note": "외부 goalbuddy 보조 → 글로벌 원위치",
     "total": 5.7
    },
    "agent:goal-scout": {
     "core_fit": 5,
     "uniqueness": 6,
     "evidence": 5,
     "cost": 8,
     "verdict": "REMOVE",
     "note": "외부 goalbuddy 보조 → 글로벌 원위치",
     "total": 5.7
    },
    "agent:goal-worker": {
     "core_fit": 5,
     "uniqueness": 6,
     "evidence": 5,
     "cost": 8,
     "verdict": "REMOVE",
     "note": "외부 goalbuddy 보조 → 글로벌 원위치",
     "total": 5.7
    },
    "agent:swarm-explorer": {
     "core_fit": 7,
     "uniqueness": 7,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "프로젝트 스캔",
     "total": 6.8
    },
    "agent:swarm-monitor": {
     "core_fit": 7,
     "uniqueness": 7,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "pane 모니터",
     "total": 6.8
    },
    "agent:swarm-verifier": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "적대 2차 검증",
     "total": 7.1
    },
    "agent:vault-pm-orchestrator": {
     "core_fit": 5,
     "uniqueness": 5,
     "evidence": 4,
     "cost": 5,
     "verdict": "KEEP",
     "note": "NotebookLM vault 루프 한정",
     "total": 4.8
    },
    "agent:docs-worker": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 3,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "REBUILD authoring 중복",
     "total": 2.8
    },
    "agent:docs-verifier": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 3,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "이중리뷰 중복",
     "total": 2.8
    },
    "agent:drift-fixer": {
     "core_fit": 1,
     "uniqueness": 1,
     "evidence": 3,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "MAINTAIN 대체",
     "total": 2.1
    },
    "agent:gap-filler": {
     "core_fit": 1,
     "uniqueness": 1,
     "evidence": 3,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "REBUILD 대체",
     "total": 2.1
    },
    "agent:orphan-pruner": {
     "core_fit": 1,
     "uniqueness": 1,
     "evidence": 3,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "AUDIT 대체",
     "total": 2.1
    },
    "agent:content-fact-checker": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "PENDING",
     "note": "NotebookLM-vault 전용 가치 심사",
     "total": 3.7
    },
    "agent:adversarial-auditor": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 6,
     "verdict": "PENDING",
     "note": "이중리뷰 중복 — vault 한정 가치 심사",
     "total": 3.5
    },
    "agent:edge-enricher": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-edge-curator",
     "total": 3.7
    },
    "agent:extracted-booster": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-edge-curator",
     "total": 3.5
    },
    "agent:confidence-rebalancer": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-edge-curator",
     "total": 3.7
    },
    "agent:edge-fact-corrector": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-edge-curator",
     "total": 3.7
    },
    "agent:density-booster": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-graph-enricher",
     "total": 3.5
    },
    "agent:orphan-linker": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-graph-enricher",
     "total": 3.5
    },
    "agent:backlinks-enricher": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-graph-enricher",
     "total": 3.5
    },
    "agent:cross-vault-linker": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 2,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-graph-enricher",
     "total": 3.5
    },
    "agent:hot-cache-filler": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-graph-enricher",
     "total": 3.7
    },
    "agent:concept-populator": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-knowledge-author",
     "total": 3.7
    },
    "agent:concept-grounding": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-knowledge-author",
     "total": 3.7
    },
    "agent:adr-generator": {
     "core_fit": 4,
     "uniqueness": 5,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-knowledge-author",
     "total": 4.3
    },
    "agent:adr-audit": {
     "core_fit": 4,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-knowledge-author",
     "total": 4.1
    },
    "agent:stub-merger": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-structure-curator",
     "total": 3.5
    },
    "agent:wiki-stub-expander": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-structure-curator",
     "total": 3.5
    },
    "agent:community-labeler": {
     "core_fit": 4,
     "uniqueness": 5,
     "evidence": 4,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "→ vault-structure-curator",
     "total": 4.7
    },
    "agent:cross-cat-prefixer": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "→ vault-structure-curator",
     "total": 3.9
    },
    "agent:bases-creator": {
     "core_fit": 4,
     "uniqueness": 6,
     "evidence": 4,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "→ vault-structure-curator",
     "total": 5.0
    },
    "hook:guard-destructive.py": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 9,
     "cost": 8,
     "verdict": "CORE",
     "note": "35+ 패턴, 13 tests",
     "total": 8.6
    },
    "hook:codex-conductor-guard.py": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "conductor 강제, 8 tests",
     "total": 8.0
    },
    "hook:pre-bash-guard.sh": {
     "core_fit": 8,
     "uniqueness": 7,
     "evidence": 8,
     "cost": 9,
     "verdict": "CORE",
     "note": "TUI/ruff-fix/SSL 차단",
     "total": 7.9
    },
    "hook:pre-edit-composition-root.sh": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 9,
     "cost": 9,
     "verdict": "CORE",
     "note": "276-test 사고 기반",
     "total": 8.8
    },
    "hook:pre-reviewer-write.sh": {
     "core_fit": 9,
     "uniqueness": 9,
     "evidence": 8,
     "cost": 9,
     "verdict": "CORE",
     "note": "리뷰어 sandbox 벽",
     "total": 8.8
    },
    "hook:preflight-path.sh": {
     "core_fit": 7,
     "uniqueness": 6,
     "evidence": 7,
     "cost": 9,
     "verdict": "KEEP",
     "note": "세션 경로 검증",
     "total": 7.1
    },
    "hook:post-deploy-verify.sh": {
     "core_fit": 7,
     "uniqueness": 7,
     "evidence": 6,
     "cost": 9,
     "verdict": "KEEP",
     "note": "deploy smoke",
     "total": 7.1
    },
    "hook:doc-sync-update.sh": {
     "core_fit": 8,
     "uniqueness": 7,
     "evidence": 4,
     "cost": 9,
     "verdict": "CORE",
     "note": "그래프 신선도 watcher (신규)",
     "total": 7.1
    },
    "hook:graphify_update.sh": {
     "core_fit": 5,
     "uniqueness": 4,
     "evidence": 4,
     "cost": 9,
     "verdict": "PENDING",
     "note": "doc-sync-update 와 중복 심사",
     "total": 5.1
    },
    "hook:notebooklm_delete_gate.sh": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 5,
     "cost": 9,
     "verdict": "KEEP",
     "note": "파괴적 삭제 게이트",
     "total": 7.2
    },
    "hook:pm_final_report.sh": {
     "core_fit": 5,
     "uniqueness": 5,
     "evidence": 4,
     "cost": 9,
     "verdict": "KEEP",
     "note": "vault 세션 리포트",
     "total": 5.4
    }
   }
  },
  {
   "round": 1,
   "label": "round-1 dual cross-score (claude+codex merged; |Δ|>2→min; verdict=consensus|fixed|claude-flagged)",
   "generated": "2026-06-06",
   "assets": {
    "agent:adr-audit": {
     "core_fit": 4,
     "uniqueness": 3,
     "evidence": 4,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "ADR 교정 방법론(cite/weaken/remove + >40% flag)은 보존 가치 있으나 concept-grounding 과 동일 패턴 — CEO 확정대로 vault-knowledge-author 흡수 | codex: Fixed merge target: vault-knowledge-author. ADR correction is useful but too narrow and overlaps content audit/grounding.",
     "total": 4.1
    },
    "agent:adr-generator": {
     "core_fit": 4,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "ADR 생성 역할은 유효하나 본문이 sportic/pickl/agri 타깃 하드코딩(이식성 결함) — vault-knowledge-author 흡수 시 일반화 필수 (CEO 확정) | codex: Fixed merge target: vault-knowledge-author. ADR bootstrap is a subroutine, not a standalone core agent.",
     "total": 4.1
    },
    "agent:adversarial-auditor": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "PENDING 판정: 고유 잔여 = 보정 오프셋 표 + SystemRandom seed 독립뿐 — 나머지는 vault-score 가 가진 동일 10-dim 루브릭 재계산이고 독립 적대 리뷰 패턴은 adversarial-review-loop 가 원조. 사용 0~1회. vault-score audit 모드로 오프셋 표 흡수 후 파일 삭제 | codex: Weak command/selftest evidence; strict re-score duplicates score scripts, doc-management AUDIT, and dual-review pattern.",
     "total": 2.8
    },
    "agent:auto-pilot-claude-reviewer": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "contract-loop cold reviewer 강화판 — tests/test_sandbox.py:40-42 frontmatter 검증, pre-reviewer-write.sh 훅 hooks.json 실배선, ticket SHA + atomic review.json 프로토콜. 명명 혼선 P1 참조 | codex: Hardened reviewer contract with ticket boot, schema output, hook sandbox tests. Orchestrator wiring evidence is still incomplete.",
     "total": 8.4
    },
    "agent:auto-pilot-codex-reviewer": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "diff-SHA freeze + 4-layer sandbox codex 리뷰어 — pm-orchestrator.md:253 이 실제 dispatch, test_dispatch/test_sandbox 존재. prompt-injection 방어(diff=DATA) 명시 | codex: Hardened Codex reviewer adds frozen diff SHA and read-only sandbox checks. Strong asset despite partial live-loop wiring.",
     "total": 8.4
    },
    "agent:backlinks-enricher": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "인바운드 링크 ≥2 보장 — orphan-linker/density-booster 와 거의 동일한 링크 작업, 본문도 generic boilerplate → vault-graph-enricher (CEO 확정) | codex: Fixed merge target: vault-graph-enricher. Backlink repair is one graph enrichment mode.",
     "total": 2.8
    },
    "agent:bases-creator": {
     "core_fit": 4,
     "uniqueness": 6,
     "evidence": 4,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "유일한 .base 대시보드 생성기지만 UX 부가층, 단일 구조 작업 — vault-structure-curator 흡수 (CEO 확정) | codex: Fixed merge target: vault-structure-curator. Obsidian Bases are export UX, but standalone agent is too small.",
     "total": 5.0
    },
    "agent:claude-reviewer": {
     "core_fit": 7,
     "uniqueness": 4,
     "evidence": 7,
     "cost": 8,
     "verdict": "KEEP",
     "note": "skill-모드(인라인 prompt → 텍스트 verdict) cold reviewer — substance 는 review-core.md SoT 로 auto-pilot-claude-reviewer 와 공유, 프로토콜만 다름. commands/auto-pilot.md:71 + pm-orchestrator.md:17 이 여전히 이 이름으로 dispatch — 장기적으로 출력모드 2개 가진 단일 리뷰어로 통일 후보 | codex: Legacy fallback reviewer still referenced by auto-pilot docs, but overlaps hardened Claude reviewer and lacks schema-first contract.",
     "total": 6.4
    },
    "agent:code-perfector": {
     "core_fit": 5,
     "uniqueness": 4,
     "evidence": 2,
     "cost": 3,
     "verdict": "KEEP",
     "note": "원샷 scan→fix→verify→document→commit 정리 파이프라인 — contract 루프와 별개의 단발 도구. 배선 약함: roster(CLAUDE.md:28) + dashboard regex(build_dashboard_data.py:34)뿐, 테스트/훅 없음 | codex: Optional cleanup helper only. Broad git add/commit/push pipeline is weakly wired and high-risk as autonomous core.",
     "total": 3.8
    },
    "agent:codex-adversarial": {
     "core_fit": 7,
     "uniqueness": 4,
     "evidence": 7,
     "cost": 8,
     "verdict": "KEEP",
     "note": "skill-모드 codex 리뷰어 — auto-pilot-codex-reviewer 와 페어 중복이나 프로토콜 상이(인라인/텍스트 vs ticket/JSON). commands/auto-pilot.md:71, pm-orchestrator.md:17 이 이 이름으로 dispatch — claude-reviewer 와 같은 통일 후보 | codex: Legacy fallback Codex reviewer remains referenced, but overlaps hardened Codex reviewer and has weaker enforcement.",
     "total": 6.4
    },
    "agent:community-labeler": {
     "core_fit": 4,
     "uniqueness": 4,
     "evidence": 4,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "'Community N' → 의미 라벨 — 형제 워커 중 유일하게 ticket_system 테스트/예제에 등장(test_ticket_system.py, ticket_system.py:10,179)하나 단일 구조 작업 → vault-structure-curator (CEO 확정) | codex: Fixed merge target: vault-structure-curator. Labeling is a structural cleanup mode with modest selftest evidence.",
     "total": 4.5
    },
    "agent:concept-grounding": {
     "core_fit": 4,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "concept claim 교정(cite/weaken/remove + verification_status frontmatter) — adr-audit 와 동일 교정 패턴 → vault-knowledge-author (CEO 확정) | codex: Fixed merge target: vault-knowledge-author. Valuable correction recipe, but depends on content-fact-checker output.",
     "total": 4.1
    },
    "agent:concept-populator": {
     "core_fit": 4,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "god-node 기반 concept/entity 페이지 부트스트랩 — authoring 계열 중복 → vault-knowledge-author (CEO 확정) | codex: Fixed merge target: vault-knowledge-author. Concept/entity bootstrapping is one knowledge-authoring mode.",
     "total": 4.1
    },
    "agent:confidence-rebalancer": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "EXT/INF/AMB 밴드 재조정 — edge 4종(edge-enricher/edge-fact-corrector/extracted-booster) 과 같은 edge-confidence 표면 → vault-edge-curator (CEO 확정) | codex: Fixed merge target: vault-edge-curator. Confidence band repair is edge-curation, not standalone core.",
     "total": 3.5
    },
    "agent:content-fact-checker": {
     "core_fit": 4,
     "uniqueness": 6,
     "evidence": 4,
     "cost": 6,
     "verdict": "KEEP",
     "note": "PENDING 판정: KEEP — raw NotebookLM 원문 대조 grounding(edge 토큰 공출현, concept claim, ADR fidelity, label fit, cross-vault real 타깃)은 doc-management 가 다루는 corpus(repo docs↔code)와 다른 vault 전용 가치이며, 통합 교정 에이전트들(vault-knowledge-author/vault-edge-curator)의 입력(content-audit-rN.md) 생산자. vault-score content-verify 모드의 엔진으로 존속. 단 실사용 0~1회 — evidence 낮게 채점 | codex: Shows NotebookLM-vault-only value: raw fulltext ed",
     "total": 4.8
    },
    "agent:cross-cat-prefixer": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "merge ID 충돌 해소 유일하나 단발 merge-step 작업 → vault-structure-curator (CEO 확정) | codex: Fixed merge target: vault-structure-curator. Namespace collision repair is a structure-curation mode.",
     "total": 3.9
    },
    "agent:cross-vault-linker": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 2,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "Vault federation links — dispatch wired (notebooklm.py:269) but hardcodes sibling vault names; merge into vault-graph-enricher per CEO. | codex: Fixed decision: fold cross-vault behavior into vault-graph-enricher; only PM-table mention, no direct command/test wiring.",
     "total": 3.5
    },
    "agent:density-booster": {
     "core_fit": 3,
     "uniqueness": 2,
     "evidence": 4,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "File admits it IS edge-enricher with cat scoping (density-booster.md:22 'Same algorithm as edge-enricher but ONLY touch listed cats') — one agent + scope param suffices. | codex: Fixed decision: same graph-density role as graph enricher/edge enricher; weak fixture-only evidence.",
     "total": 3.4
    },
    "agent:docs-verifier": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 3,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "6-dim doc rubric cross-check — doc-management AUDIT + dual adversarial review cover this; PM-mode mention only (vault-pm-orchestrator.md:24), no dispatch code/test. | codex: Fixed decision and doc-core supremacy: doc-management AUDIT/dual review replaces this docs-worker verifier.",
     "total": 2.8
    },
    "agent:docs-worker": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 4,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "Scoped doc-page authoring — doc-management REBUILD replaces; has real dispatch wiring (code.py:154) that removal must also unwire. | codex: Fixed decision and doc-core supremacy: doc-management REBUILD replaces per-module doc authoring.",
     "total": 3.0
    },
    "agent:drift-fixer": {
     "core_fit": 2,
     "uniqueness": 1,
     "evidence": 4,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "Best-wired of the vault doc trio (fix.py routing + drift.py + test_dispatch.py) but claim/symbol drift repair = doc-management MAINTAIN; removal needs same-change pipeline rerouting. | codex: Fixed decision: doc-management MAINTAIN replaces stale signature/doc drift fixing.",
     "total": 2.8
    },
    "agent:edge-enricher": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 2,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "No live dispatch route — WORKER_FOR_DIM sends graph_density to density-booster instead (notebooklm.py:265); only selftest.py:38 lists it. Effectively orphaned. | codex: Fixed decision: fold edge enrichment into vault-edge-curator; PM-only wiring.",
     "total": 3.2
    },
    "agent:edge-fact-corrector": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 4,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "Best-specified vault edge worker (re-verify before action, AMB 15% cap, atomic write, idempotent); demotion role distinct but same edge-store domain → vault-edge-curator per CEO. | codex: Fixed decision: fold edge correction into vault-edge-curator; content-fact-checker references it, limited tests.",
     "total": 3.9
    },
    "agent:extracted-booster": {
     "core_fit": 3,
     "uniqueness": 2,
     "evidence": 2,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "INF→EXT promotion = inverse of edge-fact-corrector's demotion on the same store; no code dispatch route (confidence_balance→confidence-rebalancer, notebooklm.py:266) — only a prose mention in vault-pm-orchestrator.md:133. | codex: Fixed decision: fold grounded-edge promotion into vault-edge-curator; overlaps confidence/edge curation.",
     "total": 3.0
    },
    "agent:gap-filler": {
     "core_fit": 2,
     "uniqueness": 1,
     "evidence": 4,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "Undocumented-module page creation = doc-management REBUILD; well-wired (fix.py:33 + test_dispatch.py:21 + drift.py:65) so removal must unwire the pipeline in the same change. | codex: Fixed decision and doc-core supremacy: doc-management REBUILD replaces generated gap pages.",
     "total": 2.8
    },
    "agent:goal-judge": {
     "core_fit": 4,
     "uniqueness": 2,
     "evidence": 4,
     "cost": 8,
     "verdict": "REMOVE",
     "note": "Exact duplicate of global ~/.claude/agents/goal-judge.md (verified present); serves EXTERNAL goalbuddy skill, spec explicitly reverts it (design spec line 96) — plugin copy goes. | codex: Fixed decision: local GoalBuddy copy should be removed; global original stays.",
     "total": 4.1
    },
    "agent:goal-scout": {
     "core_fit": 4,
     "uniqueness": 2,
     "evidence": 4,
     "cost": 8,
     "verdict": "REMOVE",
     "note": "Duplicate of global ~/.claude/agents/goal-scout.md (verified present); external-goalbuddy helper, out of coding-system scope per spec line 96. | codex: Fixed decision: local GoalBuddy copy should be removed; global original stays.",
     "total": 4.1
    },
    "agent:goal-worker": {
     "core_fit": 4,
     "uniqueness": 2,
     "evidence": 4,
     "cost": 8,
     "verdict": "REMOVE",
     "note": "Duplicate of global ~/.claude/agents/goal-worker.md (verified present); bounded-writer contract is solid but belongs to the external goalbuddy skill. | codex: Fixed decision: local GoalBuddy copy should be removed; global original stays.",
     "total": 4.1
    },
    "agent:harness-evaluator": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "3-agent harness gate ③ — dual-mode (contract review pre-code + Playwright app QA post-code) with hard per-criterion thresholds and anti-generosity tuning; wired via commands/harness-qa.md:6. | codex: Core autonomous coding loop QA role; wired by /harness-qa and setup-harness asset list.",
     "total": 7.8
    },
    "agent:harness-generator": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "Harness stage ② — sprint-contract negotiation + scoped build with write-set discipline; wired via commands/harness-build.md:5; depends on project-side guard scripts setup-harness installs. | codex: Core autonomous coding loop builder role; wired by /harness-build and setup-harness asset list.",
     "total": 7.8
    },
    "agent:harness-planner": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "CORE",
     "note": "Harness stage ① — short prompt → ambitious-but-bounded spec.md with sprint table + interface/invariant cues; merge-mode idempotent; wired via commands/harness-plan.md:6. | codex: Core autonomous coding loop planner role; wired by /harness-plan and setup-harness asset list.",
     "total": 7.8
    },
    "agent:hot-cache-filler": {
     "core_fit": 3,
     "uniqueness": 4,
     "evidence": 4,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "hot.md population from graphify analysis — dispatch wired (notebooklm.py:270) and code.py seeds its placeholder sections; folds into vault-graph-enricher per CEO. | codex: Fixed decision: fold hot cache population into vault-graph-enricher; PM-only wiring.",
     "total": 3.9
    },
    "agent:orphan-linker": {
     "core_fit": 3,
     "uniqueness": 2,
     "evidence": 3,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "CEO fixed → vault-graph-enricher. Wiring is name-list only (vault/scripts/selftest.py:39); no auto-plan route in notebooklm.py WORKER_FOR_DIM. | codex: Fixed decision: merge graph-link repair behavior into vault-graph-enricher; current evidence is only legacy vault mapping/selftest-level wiring.",
     "total": 3.2
    },
    "agent:orphan-pruner": {
     "core_fit": 2,
     "uniqueness": 1,
     "evidence": 4,
     "cost": 6,
     "verdict": "REMOVE",
     "note": "CEO fixed REMOVE (doc-management replaces dead-ref pruning). Caveat: has LIVE wiring (fix.py:34 map, drift.py:66, test_fix_verify_export.py:41) — must de-wire in the same change. | codex: Fixed decision and doc-core supremacy: orphan drift repair duplicates doc-management AUDIT/MAINTAIN despite legacy fix.py/vault-build wiring.",
     "total": 2.8
    },
    "agent:pm-orchestrator": {
     "core_fit": 10,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 6,
     "verdict": "CORE",
     "note": "Pillar-① contract itself. All cited helpers verified real: _contract/_dispatch/_worktree.compute_merge_conflict_finding_hash:359/_reviewer_wrapper.spawn:41/orchestrator.py pivot-check. Wired at skills/auto-pilot/SKILL.md:116. Cost down-weighted: 290-line doc tightly coupled to scripts = drift surface. | codex: Central PM-worker-review contract with skill, README, dispatch protocol, state helper, a",
     "total": 8.5
    },
    "agent:retro": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 5,
     "cost": 8,
     "verdict": "CORE",
     "note": "Only run→memory distiller (pillar ③); append-only .claude/insights.md, no-verdict discipline explicit. Wired at skills/auto-pilot/SKILL.md:67 + pm-orchestrator.md:98 but dispatch is optional (\"MAY\") and zero tests — evidence stays 5. | codex: Strong knowledge-persistence fit and referenced by PM/skill/spec, but mostly prompt-level with little executable/test evidence.",
     "total": 7.4
    },
    "agent:security-reviewer": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Only trust-boundary specialist that actually exists. Hard wiring: scripts/_dispatch.py:19-20 _VALID_ROLES, schemas/ticket.schema.json role enum, hooks/pre-reviewer-write.sh, tests/test_dogfood_gate.py:216. | codex: Safety pillar specialist; wired in PM/skill, ticket role allowlist, reviewer-write hook allowlist, and specialist output gate tests.",
     "total": 8.0
    },
    "agent:specialist-pool": {
     "core_fit": 6,
     "uniqueness": 6,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "Routing lookup table, self-declared non-runnable. 4/5 Tier-2 rows are TBD agents absent from agents/ (verified). Referenced by skills/auto-pilot/SKILL.md + pm-orchestrator.md hard rule 7 + build_dashboard_data.py. | codex: Useful thin registry for specialist dispatch, but partly overlaps PM/security docs and includes TBD entries that are not real agents.",
     "total": 6.3
    },
    "agent:stub-merger": {
     "core_fit": 3,
     "uniqueness": 2,
     "evidence": 2,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "CEO fixed → vault-structure-curator. Weakest wiring of the trio: only the selftest.py:40 name list; not in notebooklm.py auto-plan map (wiki_articles routes to wiki-stub-expander only). | codex: Fixed decision: merge stub consolidation into vault-structure-curator; current asset is one narrow NotebookLM vault worker.",
     "total": 3.0
    },
    "agent:swarm-explorer": {
     "core_fit": 7,
     "uniqueness": 7,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "CEO fixed: swarm agents 3 KEEP. Actually executed in swarm bootstrap (swarm/scripts/run-pm.sh:74) + skills/swarm/SKILL.md:12 + swarm-ticket SKILL. | codex: Fixed swarm-agent keep; maps codebases for swarm bootstrap, but run-pm uses pm-explore prompt rather than clearly spawning this agent.",
     "total": 7.0
    },
    "agent:swarm-monitor": {
     "core_fit": 6,
     "uniqueness": 7,
     "evidence": 5,
     "cost": 8,
     "verdict": "KEEP",
     "note": "CEO fixed: swarm agents 3 KEEP. Delegated from skills/swarm-status/SKILL.md:38 as the deep-diagnostic tier; read-only, one-shot report, no loop. | codex: Fixed swarm-agent keep; useful health diagnostic, but evidence is weak because start.sh does not wire the monitor pane and only swarm-status references Task dispatch.",
     "total": 6.4
    },
    "agent:swarm-verifier": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 8,
     "verdict": "KEEP",
     "note": "CEO fixed: swarm agents 3 KEEP. pm-verify.md:5-7 names it the implementation; rubric-dim coherence covered by swarm/tests/rubric/test_rubric_coherence.sh:11. | codex: Fixed swarm-agent keep; pm-verify delegates to it, verify schema exists, and rubric coherence test covers the agent.",
     "total": 7.4
    },
    "agent:tdd-enforcer": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Test-first hard gate with delete-and-restart semantics. Wired: _dispatch.py:20 role, ticket.schema.json enum, hooks/pre-reviewer-write.sh, skills/auto-pilot/SKILL.md + commands/auto-pilot-server.md. | codex: Core enforcement gate for runtime-code diffs; wired in PM/skill, ticket role allowlist, and reviewer-write hook allowlist.",
     "total": 8.0
    },
    "agent:tech-critic-lead": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Pre-dispatch \"기능은 비용\" CTO gate — the only gate that fires BEFORE workers. Wired: _dispatch.py:20, ticket schema, scripts/_gc.py, hooks/pre-reviewer-write.sh, commands/auto-pilot-server.md. | codex: Pre-worker scope/value gate is central to safety and cost control; wired in PM/skill, ticket role allowlist, hooks, and GC/test references.",
     "total": 8.0
    },
    "agent:vault-pm-orchestrator": {
     "core_fit": 5,
     "uniqueness": 6,
     "evidence": 5,
     "cost": 4,
     "verdict": "KEEP",
     "note": "CEO fixed KEEP. Real wiring (commands/vault-build.md:150 dispatch, vault/pipeline/loop.py, pm_loop.py, selftest). Cost low: 280-line file whose dispatch tables name ~15 workers now slated REMOVE/INTEGRATE — heavy rewrite due. | codex: Fixed decision: keep as vault PM, but it is bloated and stale, still mapping removed/integrated legacy workers and retired repo-doc flows.",
     "total": 5.1
    },
    "agent:wiki-stub-expander": {
     "core_fit": 3,
     "uniqueness": 2,
     "evidence": 4,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "CEO fixed → vault-structure-curator. Slightly better wired than stub-merger: notebooklm.py:271 auto-plan maps wiki_articles → wiki-stub-expander; integration must update that map + selftest.py:40. | codex: Fixed decision: merge stub expansion into vault-structure-curator; current evidence is legacy vault selftest/PM table-level only.",
     "total": 3.4
    },
    "agent:worker": {
     "core_fit": 10,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Implementation half of pillar ①. Ticket-boot sequence verified against scripts/_subagent_helpers.py (read_ticket:21, assert_not_canceled:33, atomic_write_output:51, write_exit_code:58, mark_done:69); role \"worker\" in _dispatch.py:19 + ticket schema. Frontmatter name auto-pilot-worker is unused as subagent_type (dispatch = general-purpose + TICKET). | codex: Core implementation actor for the autono",
     "total": 8.8
    },
    "codex-skill:codex-orchestra": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "KEEP",
     "note": "Codex-seat sibling of CORE Claude skill; self-authored; full plan→implement→review loop with fail-closed rules (SKILL.md:106-113) | codex: Direct Codex-side PM-worker-review loop; hook and tests support the conductor contract.",
     "total": 8.4
    },
    "codex-skill:diagnose": {
     "core_fit": 5,
     "uniqueness": 4,
     "evidence": 5,
     "cost": 8,
     "verdict": "KEEP",
     "note": "feedback-loop-first debugging discipline for the Codex worker seat; explicitly defers to superpowers:systematic-debugging when both active (SKILL.md:19) | codex: Useful debugging loop, but overlaps superpowers debugging and existing diagnosing-* skills; mostly metadata evidence.",
     "total": 5.2
    },
    "codex-skill:grill-with-docs": {
     "core_fit": 6,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 8,
     "verdict": "KEEP",
     "note": "design-time grilling interview, lazy CONTEXT.md/ADR creation; NOT a stale-doc REBUILD/MAINTAIN/AUDIT duplicate so doc-core supremacy does not fire | codex: Plan-vs-docs grilling overlaps improve-codebase-architecture and doc-management-adjacent ADR workflows.",
     "total": 5.0
    },
    "codex-skill:handoff": {
     "core_fit": 6,
     "uniqueness": 6,
     "evidence": 5,
     "cost": 9,
     "verdict": "KEEP",
     "note": "weak ③ — writes to OS tmp only (SKILL.md:30-31), never feeds vault/memory, so persistence is ephemeral by design | codex: Supports knowledge persistence and session continuity; cheap, but evidence is mostly references and metadata.",
     "total": 6.2
    },
    "codex-skill:improve-codebase-architecture": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "cross-runtime fork of Claude-side skill (round-0 KEEP) — same deep-module/deletion-test methodology, Codex seat only; runtime boundary blocks INTEGRATE | codex: Good architecture-review fit, but duplicates the Claude-side plugin skill and has limited Codex-specific wiring.",
     "total": 6.1
    },
    "codex-skill:migrate-to-codex": {
     "core_fit": 4,
     "uniqueness": 9,
     "evidence": 6,
     "cost": 4,
     "verdict": "KEEP",
     "note": "only asset that provisions the Codex worker seat from Claude config; 919-line Apache-2.0 Python fork = heaviest maintenance in chunk; pycache proves real execution; path bug P2 | codex: Unique migration bridge with real CLI code; no clear test coverage and carries higher maintenance burden.",
     "total": 5.7
    },
    "codex-skill:prototype": {
     "core_fit": 3,
     "uniqueness": 6,
     "evidence": 3,
     "cost": 9,
     "verdict": "KEEP",
     "note": "weakest pillar fit in chunk — generic throwaway-prototype discipline, loop-adjacent at best; cheap md+2 refs so retention cost ~0 | codex: Generic exploration aid; low 4-pillar fit but cheap and not doc-management duplicate.",
     "total": 4.7
    },
    "codex-skill:tdd": {
     "core_fit": 6,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "Codex-seat counterpart of agent:tdd-enforcer (CORE) discipline; defers to superpowers:test-driven-development when active (SKILL.md:19) — cooperates, not duplicates | codex: Supports safety through test-first work, but overlaps tdd-enforcer and global TDD skills.",
     "total": 6.1
    },
    "codex-skill:to-issues": {
     "core_fit": 5,
     "uniqueness": 6,
     "evidence": 3,
     "cost": 8,
     "verdict": "KEEP",
     "note": "vertical-slice ticket generation feeding the loop's ticket model; HITL/AFK typing is unique; soft dep on unmanaged setup-matt-pocock-skills (SKILL.md:34) | codex: Useful PM slicing primitive for worker tickets; weak direct wiring and depends on external tracker conventions.",
     "total": 5.3
    },
    "codex-skill:to-prd": {
     "core_fit": 4,
     "uniqueness": 6,
     "evidence": 3,
     "cost": 8,
     "verdict": "KEEP",
     "note": "planning front-end of the loop pipeline (conversation→PRD→to-issues); no-interview rule (SKILL.md:27) keeps it cheap | codex: Planning capture is useful but not central to the autonomous loop; only metadata/README evidence.",
     "total": 4.9
    },
    "codex-skill:triage": {
     "core_fit": 5,
     "uniqueness": 4,
     "evidence": 3,
     "cost": 8,
     "verdict": "KEEP",
     "note": "only issue-triage state machine in the whole asset inventory; AI-disclaimer + label-role vocabulary well specified; has explicit fallback when setup-matt-pocock-skills absent (SKILL.md:58) | codex: Issue state-machine helps routing and safety, but overlaps review-loop triage and setup label docs.",
     "total": 4.8
    },
    "codex-skill:zoom-out": {
     "core_fit": 4,
     "uniqueness": 2,
     "evidence": 3,
     "cost": 9,
     "verdict": "KEEP",
     "note": "context-map for the Codex worker seat; on Claude seat graphify query/Explore already do this better — value is Codex-only and modest | codex: Explanatory system map is nearly a preflight mode of improve-codebase-architecture.",
     "total": 4.0
    },
    "command:auto-pilot": {
     "core_fit": 10,
     "uniqueness": 8,
     "evidence": 9,
     "cost": 8,
     "verdict": "CORE",
     "note": "Interactive entry + unique preflight gates (git≥2.32, subagent discovery probe, codex sandbox probe, degraded-mode fallback); orchestrator.py + 30 tests | codex: Primary PM-worker-reviewer loop entrypoint; strongly wired through skill, orchestrator, hooks, reviewer agents, and tests.",
     "total": 9.0
    },
    "command:auto-pilot-server": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Headless driver entry; scripts/headless-loop.py real + 27 tests (tests/test_headless_loop.py) + reused by evals runner/dogfood scripts | codex: Core headless autonomous loop; backed by scripts/headless-loop.py and tests/test_headless_loop.py, with higher upkeep from permissions/cost controls.",
     "total": 8.4
    },
    "command:eval-run": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Evals layer entry; scripts/evals/cli.py + 5 test files (test_evals_*) + 2 design specs. P1: relative path makes it repo-root-bound | codex: Advisory eval harness matches the measure-before-believing pillar and has runner/oracle/aggregate tests.",
     "total": 8.0
    },
    "command:harness-build": {
     "core_fit": 6,
     "uniqueness": 4,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness build (CEO 8→2). agents/harness-generator.md exists; contract-before-code flow intact | codex: Useful harness stage but fixed decision folds harness commands into /harness routing.",
     "total": 5.8
    },
    "command:harness-drift": {
     "core_fit": 6,
     "uniqueness": 4,
     "evidence": 7,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops drift (CEO 8→2). Best-wired of the ops set: allowed-tools covers BOTH project-local and plugin-root scanner with fallback logic | codex: setup-harness drift script is real and tested, but fixed decision makes it a /harness-ops mode.",
     "total": 6.0
    },
    "command:harness-loop": {
     "core_fit": 7,
     "uniqueness": 4,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops loop (CEO 8→2). harness-loop.sh exists; P1: allowed-tools whitelists project-local path but executes plugin-root path | codex: Autofix loop is useful but overlaps setup-harness operations and should become /harness-ops loop.",
     "total": 6.2
    },
    "command:harness-plan": {
     "core_fit": 6,
     "uniqueness": 4,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness plan (CEO 8→2). agents/harness-planner.md exists; proper context:fork agent dispatch | codex: Planner command overlaps the harness trio and belongs under consolidated /harness plan.",
     "total": 5.8
    },
    "command:harness-qa": {
     "core_fit": 6,
     "uniqueness": 4,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness qa (CEO 8→2). agents/harness-evaluator.md exists; mode A contract review / mode B write-set-subset + 7-criteria QA is the richest of the trio | codex: Evaluator command is useful but is a stage mode of the consolidated harness command.",
     "total": 5.8
    },
    "command:harness-score": {
     "core_fit": 6,
     "uniqueness": 4,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops score (CEO 8→2). score-harness.sh exists; P1: allowed-tools mismatch + `| jq .` pipe not whitelisted | codex: Scorer script has bats coverage but should route through /harness-ops score.",
     "total": 5.8
    },
    "command:harness-setup": {
     "core_fit": 7,
     "uniqueness": 4,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops setup (CEO 8→2). bootstrap.sh exists in skills/setup-harness/scripts/; P2: bang only echoes the command instead of executing | codex: Bootstrap belongs in /harness-ops; current command prose is useful but executable line is flawed.",
     "total": 6.2
    },
    "command:harness-verify": {
     "core_fit": 7,
     "uniqueness": 5,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ /harness-ops verify (CEO 8→2). verify-harness.sh exists; functional stdin→exit-code hook tests are real value (catches scored-high-but-dead hooks); P1 allowed-tools mismatch | codex: Functional verification is important but should be a /harness-ops verify mode.",
     "total": 6.5
    },
    "command:nbm-to-obsidian": {
     "core_fit": 2,
     "uniqueness": 1,
     "evidence": 2,
     "cost": 9,
     "verdict": "REMOVE",
     "note": "Self-described legacy alias; CEO fixed REMOVE. vault-build --source notebooklm is the canonical path | codex: Fixed decision removes this legacy alias; /vault-build --source notebooklm covers it.",
     "total": 2.8
    },
    "command:quality-loop": {
     "core_fit": 2,
     "uniqueness": 1,
     "evidence": 6,
     "cost": 9,
     "verdict": "REMOVE",
     "note": "Pure thin wrapper; CEO fixed REMOVE. adversarial-review-loop skill auto-triggers on the identical phrases ('quality loop', '95점', 'score this project') | codex: Fixed decision removes this pure alias because adversarial-review-loop codebase mode covers it.",
     "total": 3.6
    },
    "command:setup-claude-md": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 5,
     "cost": 8,
     "verdict": "KEEP",
     "note": "Prohibition-mining method (git log fix/revert/hotfix → incident-referenced 금지 table) unique; referenced in docs/architecture.md + unified-coding-system design spec | codex: Unique prohibition-mining workflow for CLAUDE.md, but evidence is mostly command prose rather than executable tests.",
     "total": 7.0
    },
    "command:sha-deploy-init": {
     "core_fit": 7,
     "uniqueness": 7,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "All 4 templates verified in deploy/templates/ (python-pm2, nextjs-pm2, nextjs-artifact, static-rsync); cross-referenced by skills/sha-deploy-standard/SKILL.md; no template tests | codex: Deploy templates and sha-deploy skill exist; command is a useful thin workflow with modest test evidence.",
     "total": 7.0
    },
    "command:vault-audit": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "→ vault-score mode (CEO fixed). 12-line thin shell dispatching adversarial-auditor (round-0 PENDING agent, weak usage: ga4 1 run) | codex: Fixed decision makes strict vault audit a vault-score mode; standalone wrapper has weak usage evidence.",
     "total": 3.6
    },
    "command:vault-build": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 6,
     "verdict": "KEEP",
     "note": "Sole export pipeline; vault/pipeline/export.py real + test_fix_verify_export.py (9 tests) + ga4 validated run. Doc-purpose path correctly retired with explicit STOP-and-route-to-doc-management guard — DOC-CORE supremacy compliant. Cost lower: 186 lines, 5 destinations, legacy --fix-repo-docs path retained | codex: Knowledge export pipeline is the non-doc-core vault asset; export/upsert behavior ha",
     "total": 7.3
    },
    "command:vault-content-verify": {
     "core_fit": 3,
     "uniqueness": 3,
     "evidence": 3,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "→ vault-score mode (CEO fixed). 12-line thin shell dispatching content-fact-checker (round-0 PENDING agent, weak usage) | codex: Fixed decision makes content verification a vault-score mode; standalone wrapper is weak and agent evidence is limited.",
     "total": 3.6
    },
    "command:vault-dashboard": {
     "core_fit": 6,
     "uniqueness": 7,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "CEO fixed KEEP. dashboard_data.py + vault/dashboard/index.html+data.json verified + test_dashboard_data.py (3 tests). Evidence better than round-0's 4. P2 prose path drift | codex: Distinct vault telemetry/dashboard surface backed by dashboard_data.py and tests.",
     "total": 6.6
    },
    "command:vault-drift": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 6,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "DOC-CORE supremacy + CEO 10→4 math force REMOVE. The command's own header (vault-drift.md:10) declares the repo-docs path DEPRECATED → doc-management AUDIT; the residual vault-internal case is covered by vault-build upsert re-export per its own Next-step section. drift.py + 9 tests stay (used by vault-build --fix-repo-docs internals), only the command shell goes | codex: Drift scanner works, but d",
     "total": 3.5
    },
    "command:vault-restructure": {
     "core_fit": 4,
     "uniqueness": 5,
     "evidence": 4,
     "cost": 6,
     "verdict": "INTEGRATE",
     "note": "→ vault-build flag (CEO fixed). restructure_loop.py + 8 phase modules verified (command doc says 7 — P2 drift). Machine-specific one-shot migration (hardcoded sportic365/PickL mapping in _mapping.py) — low reuse | codex: Fixed decision turns this user-specific restructure workflow into vault-build flags, not a standalone command.",
     "total": 4.6
    },
    "command:vault-resume": {
     "core_fit": 4,
     "uniqueness": 4,
     "evidence": 4,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "→ vault-build flag (CEO fixed). 26-line thin shell over ticket-state.json + vault-pm-orchestrator dispatch; ticket_system.py + test exist | codex: Fixed decision folds resume behavior into vault-build/vault-score state flags.",
     "total": 4.6
    },
    "command:vault-score": {
     "core_fit": 6,
     "uniqueness": 6,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "CEO fixed KEEP as the consolidation target absorbing vault-audit + vault-content-verify as modes. score_structural.py/score_content.py/pm_loop.py all verified + test_score_content_tokens.py | codex: Surviving vault quality entrypoint with structural/content scorers and PM watchdog support.",
     "total": 6.2
    },
    "command:vault-selftest": {
     "core_fit": 8,
     "uniqueness": 6,
     "evidence": 7,
     "cost": 8,
     "verdict": "KEEP",
     "note": "CEO fixed KEEP. vault/scripts/selftest.py + test_selftest.py verified; vault/templates/rubric.yaml exists. P2: CI snippet cites wrong relative path | codex: Plugin selftest directly supports safety/enforcement and is covered by vault/tests/test_selftest.py.",
     "total": 7.3
    },
    "hook:codex-conductor-guard.py": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Marker opt-in conductor enforcement; 8/8 subprocess tests pass incl. plans-ancestor bypass regression; fail-open. | codex: Conductor-mode enforcement is directly tied to codex-orchestra; wired and covered by script tests plus repo docs.",
     "total": 8.0
    },
    "hook:doc-sync-update.sh": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 8,
     "verdict": "CORE",
     "note": "Doc-pillar flagship watcher: lazy needs_update flag + opt-in eager GRAPHIFY_AUTOSYNC; consumed by doc-management MAINTAIN (SKILL.md:105,195). No tests yet. | codex: Feeds doc-management MAINTAIN by marking graphify-out/needs_update on code edits; wired and documented, but lacks direct tests.",
     "total": 8.0
    },
    "hook:graphify_update.sh": {
     "core_fit": 4,
     "uniqueness": 2,
     "evidence": 4,
     "cost": 7,
     "verdict": "INTEGRATE",
     "note": "Resolves round-0 PENDING → INTEGRATE into doc-sync-update.sh as a vault-md branch. Same watcher concept, but eager SYNC `graphify update` inside PostToolUse (latency) vs doc-sync's lazy flag; no tests; doc-sync-update.sh:5 itself says it generalized from this. | codex: Legacy raw/sources markdown graph updater overlaps the doc-management/doc-sync freshness path under DOC-CORE supremacy.",
     "total": 4.0
    },
    "hook:guard-destructive.py": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Safety-pillar anchor: 17-pattern deny table, heredoc/-m scrub, hour-marker override; 13-case runner but currently 7/13 on this machine (live TMPDIR marker flips DENY→ALLOW — env, not logic); real-world use proven (PickL deploy sessions). | codex: Broad destructive-command gate with hooks.json wiring and 13 script-style regression cases.",
     "total": 8.4
    },
    "hook:notebooklm_delete_gate.sh": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 9,
     "verdict": "KEEP",
     "note": "Confirm-gated NotebookLM deletes, dual-wired (Bash CLI + MCP tool_name shape — the round-2 fail-open regression is test-pinned); 9/9 runner passes. | codex: NotebookLM-specific delete confirmation gate; wired for Bash and MCP forms and covered by direct tests.",
     "total": 7.8
    },
    "hook:pm_final_report.sh": {
     "core_fit": 5,
     "uniqueness": 6,
     "evidence": 4,
     "cost": 8,
     "verdict": "KEEP",
     "note": "Stop-time vault PM report — only mechanism that covers interrupted sessions, serves vault-pm-orchestrator (CEO: KEEP). Env-gated (NBM_VAULT_PATH) so zero cost when vault loop inactive; header comment stale (.pm-active never checked, cites /nbm-to-obsidian slated REMOVE); no tests. | codex: Cheap Stop hook for vault PM ticket summaries; wired but weakly evidenced and vault-legacy shaped.",
     "total": 5.5
    },
    "hook:post-deploy-verify.sh": {
     "core_fit": 6,
     "uniqueness": 7,
     "evidence": 7,
     "cost": 8,
     "verdict": "KEEP",
     "note": "Warn-only post-deploy smoke (zombie ports, placeholder .env values); 5 pytest cases pass; insight-derived. Limits: hardcoded port list, every `git push` counts as deploy, cwd-relative .env only. | codex: Non-blocking deploy smoke watcher for port zombies and placeholder env leaks; wired and covered in tests/test_hooks.py.",
     "total": 6.8
    },
    "hook:pre-bash-guard.sh": {
     "core_fit": 8,
     "uniqueness": 6,
     "evidence": 8,
     "cost": 9,
     "verdict": "CORE",
     "note": "3 incident-derived deny rules (claude-doctor TUI hang, ruff --fix on composition roots, chained SSL config); ~8 pytest cases pass; AUTO_PILOT_BASH_BYPASS escape. Gap: ruff regex misses flag-reordered forms. | codex: Blocks known workflow footguns not covered by guard-destructive; wired and tested for TUI, ruff-fix, SSL, bypass.",
     "total": 7.7
    },
    "hook:pre-edit-composition-root.sh": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 9,
     "cost": 9,
     "verdict": "CORE",
     "note": "276-test-incident guard; content-aware (new/empty __init__.py passes, TS barrel warns-not-blocks); ~10 pytest cases incl. MultiEdit shape + malformed-JSON fail-open. | codex: High-value composition-root/re-export safety gate; MultiEdit wiring and behavior are tested.",
     "total": 8.8
    },
    "hook:pre-reviewer-write.sh": {
     "core_fit": 10,
     "uniqueness": 9,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Reviewer sandbox wall: role-env-gated write scope + Bash mutation denylist + codex --sandbox read-only enforcement; 14 tests in tests/test_sandbox.py incl. hooks.json registration assert; consumed by scripts/_reviewer_wrapper.py. | codex: Reviewer sandbox wall for PM-worker-dual-review; wired, wrapper-referenced, and tested for write and Bash mutation denial.",
     "total": 9.0
    },
    "hook:preflight-path.sh": {
     "core_fit": 6,
     "uniqueness": 6,
     "evidence": 7,
     "cost": 9,
     "verdict": "KEEP",
     "note": "Warn-only SessionStart preflight: /tmp cwd, mid-loop state resume hint, vault typo dirs; 4 pytest cases pass. Vault-typo rule (Valut/Volt) is cwd-relative and near-vestigial but free. | codex: SessionStart path/state sanity guard; wired and tested for tmp cwd, running state, and vault typo warnings.",
     "total": 6.7
    },
    "skill-shell:codebase-perfection-loop": {
     "core_fit": 2,
     "uniqueness": 2,
     "evidence": 2,
     "cost": 8,
     "verdict": "REMOVE",
     "note": "Hard rule 적용: live role 없음 + pillar NONE → REMOVE. references/ 5종은 docs/ 또는 git 히스토리로 이관 후 디렉토리 삭제 (tmux-launcher.sh 는 swarm 이 대체). | codex: Deprecated shell-only provenance directory with no SKILL.md; replaced by ARL codebase mode and PM quality loop.",
     "total": 2.9
    },
    "skill:adversarial-review-loop": {
     "core_fit": 10,
     "uniqueness": 9,
     "evidence": 9,
     "cost": 5,
     "verdict": "CORE",
     "note": "리뷰/품질 엔진 본체. arl-helpers.sh + 40 bats tests (SKILL claims 38 — stale). 527줄 3-mode = 유지비 높음 (cost 5). | codex: Primary dual-review and codebase quality engine; helper scripts/tests exist, but the runbook is large and high-touch.",
     "total": 8.8
    },
    "skill:auto-pilot": {
     "core_fit": 10,
     "uniqueness": 9,
     "evidence": 9,
     "cost": 6,
     "verdict": "CORE",
     "note": "자율 루프 본체. orchestrator.py + headless-loop.py + 대규모 pytest (test_orchestrator/test_headless_loop/test_dispatch/test_state_lock 등) 실재. 참조 파일 전수 resolve 확인. | codex: Main autonomous PM-worker-review loop with command, state scripts, tests, and hook support; complex to maintain.",
     "total": 9.0
    },
    "skill:codex-orchestra": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 8,
     "cost": 8,
     "verdict": "CORE",
     "note": "Conductor 패턴 유일 보유. 외부 의존 codex-companion.mjs 경로 실재 확인 — 단 external plugin 경로 하드코딩이 잔여 리스크 (openai-codex 마켓플레이스 구조 변경 시 깨짐). | codex: Distinct conductor mode with registered codex-conductor hook and tests; strong safety/enforcement fit.",
     "total": 8.0
    },
    "skill:diagnosing-llm-output-leaks": {
     "core_fit": 6,
     "uniqueness": 8,
     "evidence": 4,
     "cost": 9,
     "verdict": "KEEP",
     "note": "진단 전용 prose 맵, 번들 스크립트/테스트/wiring 0 → evidence 4 (round-0의 5보다 보수적). 유지비 거의 0이라 KEEP 합리적. | codex: Useful low-cost diagnostic map; no meaningful wiring or tests found, so evidence is mostly runbook value.",
     "total": 6.5
    },
    "skill:diagnosing-stale-runtime": {
     "core_fit": 6,
     "uniqueness": 8,
     "evidence": 4,
     "cost": 9,
     "verdict": "KEEP",
     "note": "진단 전용 prose 맵, wiring/테스트 0 → evidence 4. residue-audit·auto-pilot 디버그 단계의 보조 지식. cost 9. | codex: Useful runtime/source mismatch diagnostic; low overlap and low cost, but not wired or tested.",
     "total": 6.5
    },
    "skill:doc-management": {
     "core_fit": 10,
     "uniqueness": 10,
     "evidence": 9,
     "cost": 7,
     "verdict": "CORE",
     "note": "Doc flagship. 번들 스크립트 2종 실재 + tests/test_doc_freshness.py 가 L3 계약 커버 + watcher hook 배선 — evidence 9. 4 references 파일 전부 실재. | codex: Flagship docs subsystem; scripts, references, tests, and doc-sync hook wiring back REBUILD/MAINTAIN/AUDIT.",
     "total": 9.4
    },
    "skill:improve-codebase-architecture": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 4,
     "cost": 8,
     "verdict": "KEEP",
     "note": "Deep-module 방법론 유일. prose-only (스크립트/테스트 0) → evidence 5. ADR/CONTEXT.md 산출이 pillar ③ 지속성에도 기여. | codex: Architecture-specific deepening workflow; valuable and cheap, but mostly prose with little executable evidence.",
     "total": 6.8
    },
    "skill:pm-quality-harness-loop": {
     "core_fit": 8,
     "uniqueness": 7,
     "evidence": 6,
     "cost": 6,
     "verdict": "KEEP",
     "note": "명시적 compose 패턴 모범. 자체 스크립트/테스트 0, 가치는 prose 시퀀싱 → evidence 6. Phase 1.5 의 엔진 호출 서술이 ARL 실계약과 불일치 (findings). | codex: Lifecycle orchestrator adds docs-sync and ship tail over ARL; useful composition, but mostly runbook evidence.",
     "total": 7.1
    },
    "skill:quality-eval": {
     "core_fit": 9,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 7,
     "verdict": "CORE",
     "note": "Rubric SoT, 소비자 3곳 (ARL/pm-loop/swarm-bench) 확인. 자체 실행 코드 없는 데이터-스킬이라 evidence 는 소비 배선으로 8. | codex: 13-dim rubric SoT used by ARL/quality-loop; important, but overlaps the newer ARL codebase mode.",
     "total": 8.1
    },
    "skill:residue-audit": {
     "core_fit": 8,
     "uniqueness": 9,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "linter 보완 유일·경계 명문화 우수. 스크립트/테스트 0, 가치는 방법론+FP 카탈로그 → evidence 6. | codex: Semantic residue audit is distinct from doc-management and linters; evidence is mostly references/runbook.",
     "total": 7.7
    },
    "skill:setup-harness": {
     "core_fit": 9,
     "uniqueness": 9,
     "evidence": 8,
     "cost": 5,
     "verdict": "CORE",
     "note": "최대 표면적 스킬 — 30 스크립트+템플릿+references → cost 5. Shipped-assets 표의 agents/·commands/ 경로가 스킬 디렉토리에 없음 (findings). | codex: Harness bootstrap has substantial scripts, templates, commands, evals, and tests; high capability but heavy surface.",
     "total": 8.2
    },
    "skill:sha-deploy-standard": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 8,
     "verdict": "KEEP",
     "note": "deploy 표준 유일 + 템플릿 실재 + 진입 커맨드 실재 → evidence 6 (사용 로그/테스트는 없음). 패턴은 PickL 실전 검증 계열. | codex: Distinct SHA deploy pattern with command/templates; peripheral to core loop but useful and cheap.",
     "total": 7.2
    },
    "skill:swarm": {
     "core_fit": 8,
     "uniqueness": 8,
     "evidence": 7,
     "cost": 5,
     "verdict": "KEEP",
     "note": "신규 채점 (round-0 은 autopilot-swarm 만). swarm/scripts (start/stop/run-pm/run-worker/lib/prompts) + swarm/tests 8개 셸 테스트 실재 → evidence 7. tmux+worktree+bus 복잡도로 cost 5. | codex: Surviving consolidated swarm entry point; backed by tmux scripts, schemas, tests, and README routing.",
     "total": 7.4
    },
    "skill:swarm-bench": {
     "core_fit": 7,
     "uniqueness": 8,
     "evidence": 6,
     "cost": 7,
     "verdict": "KEEP",
     "note": "CEO 결정대로 별기능 유지. throwaway-worktree 격리 + median/stddev 규칙 명시. 실행 증적(과거 bench 결과물)은 미확인 → evidence 6. | codex: Unique empirical comparison tool, but bench implementation is partial versus the skill contract.",
     "total": 7.1
    },
    "skill:swarm-init": {
     "core_fit": 4,
     "uniqueness": 2,
     "evidence": 5,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "CEO 6→2 결정 집행 대상. 정규화 테이블·스키마는 swarm SKILL 로 흡수 후 파일 삭제. | codex: CEO decision: fold into consolidated swarm; config schema is useful but should not remain a separate skill.",
     "total": 4.3
    },
    "skill:swarm-status": {
     "core_fit": 4,
     "uniqueness": 2,
     "evidence": 5,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "CEO 6→2 집행 대상. inline bash 절차는 흡수 시 그대로 이식 가능. | codex: CEO decision: fold into swarm; useful diagnostics but too small and overlapping as standalone.",
     "total": 4.3
    },
    "skill:swarm-stop": {
     "core_fit": 4,
     "uniqueness": 2,
     "evidence": 6,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "CEO 6→2 집행 대상. --purge 사용자 확인 규칙은 흡수 시 유지 필수 (uncommitted work 보호). | codex: CEO decision: fold into swarm; stop.sh exists, but standalone skill is a satellite.",
     "total": 4.5
    },
    "skill:swarm-ticket": {
     "core_fit": 4,
     "uniqueness": 3,
     "evidence": 5,
     "cost": 8,
     "verdict": "INTEGRATE",
     "note": "CEO 6→2 집행 대상. ticket JSON 스키마는 swarm/tests/ticket-schema 와 정합 유지하며 흡수. | codex: CEO decision: fold into swarm; manual ticket injection belongs as a swarm subcommand/flag.",
     "total": 4.5
    }
   }
  }
 ]
};

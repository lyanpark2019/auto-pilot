# Unified Coding System — design spec

> 2026-06-06. CEO-confirmed: ALL self-made coding-system assets merge into THIS plugin (auto-pilot, name kept), similar functions truly MERGED (zero duplication), docs subsystem = flagship (graphify-native, plugin directly performs doc freshness). Build = ultracode workflow + dual adversarial review loop until APPROVE.

## Goal

One plugin = complete automated AI coding system: autonomous loop, dual review, quality lift, harness bootstrap, swarm parallel execution, deploy templates, and a graphify-native documentation subsystem that keeps docs current automatically.

## Scope

IN: auto-pilot (base, evolves in place) · vault-builder (wholesale) · autopilot-swarm (wholesale) · sha-deploy (wholesale) · global coding-system skills (pm-quality-harness-loop, residue-audit, codex-orchestra, graphify-doc-rebuild) · goalbuddy agent trio · setup-claude-md + quality-loop commands · 12 codex forks (versioned under `codex/`, synced out) · PickL harness-fork improvements (upstreamed).

OUT (unchanged this round): graphify engine skill (stays global — CEO decision; non-doc uses), domain assets (sportic ×4, design ×7, yt ×2, rpc-schema-validator, sportic365-contract-drift-checker), session-infra hooks (session-skill-profile, cleanup-*), ai-content-hub token-economy fork (intentional), kb-search (project-specific). `~/.claude`/`~/.codex` deletions of moved originals happen AFTER merge verified (separate tail step).

## Architecture (subsystems)

| Subsystem | Contents | Merge action |
|---|---|---|
| core loop | skills/auto-pilot + scripts/ (orchestrator, headless-loop, _*.py) + schemas + prompts | UNCHANGED (228 tests protect it) |
| review | adversarial-review-loop + reviewer/specialist agents + tdd-enforcer + security-reviewer + tech-critic-lead | reviewer pairs: extract shared checklist → `agents/references/review-core.md`; both shells cite it; **names unchanged** (scripts/tests dispatch by name) |
| quality | quality-eval (rubric SoT) + pm-quality-harness-loop (superset) + residue-audit + quality-loop alias + code-perfector | codebase-perfection-loop SKILL.md DELETED (references/ kept — rubric provenance) |
| harness | setup-harness + harness-* commands + harness trio agents + setup-claude-md command | trio = best-of-breed: PickL fork's richer contract (Goal/Public-interface/Deep-module/Invariants/Write-set/Tests/Rollback-surface) upstreamed into generator+evaluator |
| **docs (flagship)** | graphify-doc-rebuild (rebuild entry) + doc-drift-audit (audit+claim ledger) + **NEW doc-sync** (automation) + vault/ (vault-builder export machinery) | see below |
| swarm | 6 swarm skills + 3 swarm agents + swarm/ scripts | absorbed; documented as parallel execution backend of core loop |
| deploy | sha-deploy-standard skill + sha-deploy-init command + deploy/templates | absorbed verbatim |
| conductor | codex-orchestra skill + codex-conductor-guard hook | skill moved in; guard already here (SoT) |
| goal | goal-{scout,judge,worker} agents | moved in verbatim |
| diagnostics | diagnosing-* ×2 + improve-codebase-architecture | unchanged |
| codex | codex/skills ×12 + sync-to-codex.sh | repo = SoT; one-way sync out |

## Docs subsystem — flagship design (zero duplication)

Four former tools → three roles + one export layer, no overlapping triggers:

1. **`/graphify-doc-rebuild`** (skill, moved in) — full rebuild when docs rotten. Diagnose-first gate kept. Fix known issues: `/tmp/code-only` hard-coding → repo-rooted `.graphify/code-only/`.
2. **`/doc-drift-audit`** (skill, already here) — in-place semantic audit + durable claim ledger. Gains bundled generic assets: `claim-ledger.schema.md` + `verify_claim_ledger` template (generalized from PickL) next to existing `check-doc-reference-integrity.mjs`.
3. **NEW `/doc-sync`** (skill + hook) — the "plugin directly performs doc updates" requirement:
   - Hook (PostToolUse/post-commit, generalized from vault-builder's `graphify_update.sh` + `graphify hook install` pattern): code change → deterministic code-only graph rebuild (zero LLM cost), doc-affecting change → `needs_doc_sync` flag.
   - Command flow: rebuild code-only graph → diff vs last-sync manifest → map changed modules to affected design docs → regenerate/patch those docs from graph (`graphify query`/`explain` + source read, file:line cites) → run ref-integrity guard → report. Incremental counterpart to rebuild.
4. **vault/** (export layer) — vault-builder wholesale: Obsidian/NotebookLM/bases/canvas export, rubric scoring, PM loop for vault quality. Its code-drift half is NOT deleted (wholesale promise) but `vault-drift` command header routes repo code↔doc drift to `/doc-drift-audit`; vault-drift scope = vault-internal sources. vault agents keep working; `pm-orchestrator` name collision → vault copy renamed `vault-pm-orchestrator` (+ internal ref sweep).
5. **DELETED: llm-wiki-architect** (per-module wiki = rot machine; superseded by graph-native authoring).

## Merge invariants (must not be lost — reviewers check these)

4-layer reviewer sandbox · diff SHA256 freeze · schema-valid review.json · scope-drift/scope-reduction HARD reject · tech-critic pre-gate · pivot-check (3-round stop) · atomic commit trailers · composition-root guard · cost/token/fork-bomb caps · POSIX-mv atomic ticket claim · adversarial verifier + worker weights · vault 2-rubric adaptive dispatch + 3-strike escalation + adversarial-auditor cadence · 13-dim rubric + anti-inflation citation rule · claim-ledger update-by-claim_id discipline · guard-destructive 35+ patterns + marker + scrubbing (13 tests) · goalbuddy receipt contracts.

## Structural rules

- Authors edit ONLY their assigned paths; manifests (plugin.json, hooks.json, .mcp.json, README) edited ONLY by the integrate step; authors never `git commit`.
- vault/ keeps vault-builder's internal layout intact (pipeline/, sources/, scripts/, rubrics/, templates/, dashboard/, tests/) so Python relative imports survive; `${CLAUDE_PLUGIN_ROOT}` references swept to `vault/...`.
- swarm/ likewise keeps internal layout; skills/agents lift to top level.
- README.md gains the ROUTING TABLE (task → single entry skill) — the anti-trigger-competition map.

## Verification

1. All test suites green: existing 228 (pytest+BATS), vault tests under `vault/`, hook tests, `bash -n` on all moved shell scripts, vault selftest.
2. `/reload-plugins`-equivalent structural validation (frontmatter, hooks.json schema, command/agent discovery).
3. **Dual adversarial review loop**: Codex-style adversarial + cold Claude review full branch diff vs this spec; fix; repeat until BOTH APPROVE (cap 3 rounds, then report honestly).

## Tail (after merge verified, separate commits)

~/.claude originals of moved assets deleted; guard-destructive.py/codex-conductor-guard.py/code-perfector.md in ~/.claude replaced by symlinks into plugin; ~/.codex moved-skill dups deleted + sync script run; project-local harness copies deleted (clai-api, PickL, sportic365-API — local commits, push gated); old plugin dirs (vault-builder, sha-deploy, autopilot-swarm) removed from ~/.claude/plugins; memory + handoff updated.

## Risks (honest)

- vault Python path move: import breakage risk — gated by running vault tests post-move.
- Reviewer-pair "merge" is checklist extraction, not file fusion — file fusion would break tested dispatch-by-name; this is the deepest safe dedup.
- swarm untested for 3 weeks — selftest after move, not full e2e.
- Hook symlink behavior (settings.json → symlink) verified at tail, fallback = 1-line wrapper.
- Agent count 46+ in one plugin: same as today's total across plugins; no net context increase.

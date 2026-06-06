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
| **docs (flagship)** | ONE skill **doc-management** (3 modes: REBUILD / MAINTAIN / AUDIT) + vault/ (export layer) | canonical spec = `skills/doc-management/references/doc-management-system.md`; see below |
| swarm | 6 swarm skills + 3 swarm agents + swarm/ scripts | absorbed; documented as parallel execution backend of core loop |
| deploy | sha-deploy-standard skill + sha-deploy-init command + deploy/templates | absorbed verbatim |
| conductor | codex-orchestra skill + codex-conductor-guard hook | skill moved in; guard already here (SoT) |
| goal | goal-{scout,judge,worker} agents | moved in verbatim |
| diagnostics | diagnosing-* ×2 + improve-codebase-architecture | unchanged |
| codex | codex/skills ×12 + sync-to-codex.sh | repo = SoT; one-way sync out |

## Docs subsystem — flagship (zero duplication)

Canonical design = `doc-management-system.md` (graphify-native 3-layer model: What=code graph / Why=intent / Generated mirror+review gate). **ONE skill `doc-management`** (renamed from graphify-doc-rebuild) = single entry, three modes:

1. **REBUILD** — existing proven 7-phase + gap-4 confirmed present: clean-slate `_archive/` branch (only reviewed docs go live), root-doc fresh rewrite step, `<MACHINE_READ_DOCS>` discovery slot (gate-parsed docs never move), ops verify-restore in same commit (no gap window). Fix: `/tmp/code-only` hard-coding → repo-rooted `.graphify/code-only/`.
2. **MAINTAIN** (new) — consumes STALE list from NEW `scripts/check_design_doc_freshness.py` (~60–100L, zero LLM: parse frontmatter `source_commit` → collect cited source paths → `git diff --name-only <commit>..HEAD -- <paths>` → STALE report; gate **WARN only**, never block). Per-doc refresh: re-query graph → re-read source → update cites/prose → bump `source_commit`; large batches go through dual review. **Forbidden: full-auto LLM rewrite + auto-commit.** The `hooks/doc-sync-update.sh` watcher (generalized from vault-builder's graphify_update.sh) keeps the graph fresh and feeds this mode.
3. **AUDIT** — doc-drift-audit methodology absorbed: read-only parallel fan-out, evidence precedence code>tests>CLI>config>generated>logs, stale-as-current (fix) vs correct-historical (leave), P0/P1/P2 findings; fixes delegated to MAINTAIN. Its repo-agnostic `check-doc-reference-integrity.mjs` carried as the skill's L2 guard asset.

**claim-ledger: NOT adopted** — hand-maintained JSON + manual `last_verified` bump is itself a rot pattern; SHA freshness (L3) + AUDIT replace it. No ledger assets bundled.

**DELETED skills after absorption:** `graphify-doc-rebuild` (renamed→doc-management), `doc-drift-audit` (→AUDIT mode), interim `doc-sync` (→MAINTAIN mode), `llm-wiki-architect` (per-module wiki = rot machine). Old trigger phrases live on in doc-management's description.

**vault/** = export layer (Obsidian/NotebookLM/bases/canvas + vault-quality PM loop). Its repo-code doc-purpose path (`--source code` drift/fix/rubric on repo docs) is RETIRED with a pointer to doc-management (canonical mapping: "doc-용도 제거, export 잔류"); NotebookLM/knowledge-vault building stays fully functional. `pm-orchestrator` name collision → vault copy renamed `vault-pm-orchestrator` (+ internal ref sweep).

## Nick Nisi principles (WorkOS 2026-06 talk — applied plugin-wide)

- **Evidence over trust**: worker verify reports must include SHA-256 of the full verify output log; reviewers re-run and cross-check the hash — mismatch = REJECT. (Extends worker.md, review-core.md, pm-orchestrator.md.)
- **Retro agent + memory**: NEW `agents/retro.md` — post-run transcript/state analysis → distills doom-loops, wasted tool calls, repeated findings into per-project memory (Gotchas-first, evidence-cited, append-only). PM may dispatch at phase end.
- **Skill minimization (Gotchas-first)**: skills guide around landmines, not re-teach coding; bodies ≤500 lines with bulk in `references/`. Stated as a plugin principle in CLAUDE.md.
- **Enforce with code, not prompts / fix the harness, not the output / measure with evals** — already embodied (hooks+schemas+state, harness-first doctrine, evals harness); stated explicitly in CLAUDE.md principles.

## Naming clarity (CEO: names must match the plugin, be unambiguous)

Plugin name `auto-pilot` kept. In-plugin renames: `graphify-doc-rebuild`→**doc-management** · `autopilot-swarm` skill→**swarm** · vault `pm-orchestrator`→**vault-pm-orchestrator**. Renames swept across the plugin. Dispatch-by-name agents (worker, reviewer pairs) NOT renamed — scripts/tests dispatch by name.

## Authoring standards (CEO directive)

Skill creation/edit follows `skill-creator` + `plugin-dev:skill-development` methodology (trigger-rich descriptions, progressive disclosure via references/). Plugin manifest/layout follows `plugin-dev:plugin-structure` + `plugin-dev:plugin-settings`; final structure validated by the `plugin-dev:plugin-validator` agent in Verify.

## Merge invariants (must not be lost — reviewers check these)

4-layer reviewer sandbox · diff SHA256 freeze · schema-valid review.json · scope-drift/scope-reduction HARD reject · tech-critic pre-gate · pivot-check (3-round stop) · atomic commit trailers · composition-root guard · cost/token/fork-bomb caps · POSIX-mv atomic ticket claim · adversarial verifier + worker weights · vault 2-rubric adaptive dispatch + 3-strike escalation + adversarial-auditor cadence · 13-dim rubric + anti-inflation citation rule · claim-ledger update-by-claim_id discipline · guard-destructive 35+ patterns + marker + scrubbing (13 tests) · goalbuddy receipt contracts.

## Structural rules

- Authors edit ONLY their assigned paths; manifests (plugin.json, hooks.json, .mcp.json, README) edited ONLY by the integrate step; authors never `git commit`.
- vault/ keeps vault-builder's internal layout intact (pipeline/, sources/, scripts/, rubrics/, templates/, dashboard/, tests/) so Python relative imports survive; `${CLAUDE_PLUGIN_ROOT}` references swept to `vault/...`.
- swarm/ likewise keeps internal layout; skills/agents lift to top level.
- README.md gains the ROUTING TABLE (task → single entry skill) — the anti-trigger-competition map.

## Verification

1. All test suites green: existing 228 (pytest+BATS), vault tests under `vault/`, hook tests, `bash -n` on all moved shell scripts, vault selftest.
2. `/reload-plugins`-equivalent structural validation (frontmatter, hooks.json schema, command/agent discovery) + **plugin-dev:plugin-validator agent pass** + `python3 -m py_compile` on `check_design_doc_freshness.py` + grep gates: zero claim-ledger adoption (historical mentions only), zero references to deleted skill names, swarm rename consistency.
3. **Dual adversarial review loop**: Codex-style adversarial + cold Claude review full branch diff vs this spec; fix; repeat until BOTH APPROVE (cap 3 rounds, then report honestly).

## Tail (after merge verified, separate commits)

~/.claude originals of moved assets deleted; guard-destructive.py/codex-conductor-guard.py/code-perfector.md in ~/.claude replaced by symlinks into plugin; ~/.codex moved-skill dups deleted + sync script run; project-local harness copies deleted (clai-api, PickL, sportic365-API — local commits, push gated); old plugin dirs (vault-builder, sha-deploy, autopilot-swarm) removed from ~/.claude/plugins; memory + handoff updated.

## Round 2 — consolidation & perfection loop (scope: workflow #2; round-1 reviewers MUST NOT judge the build against this section)

CEO directives: (a) similar assets truly MERGED, not co-located; (b) **EVERY asset gets an individual score + verdict**; (c) **the graphify doc-management system is THE CORE** — any skill/agent whose purpose is improving stale docs is judged against it: integrate into a mode or REMOVE. Iterate until convergence.

**Phase 0 — SCORE (before any consolidation execution):** read-only scorer fan-out produces a per-asset scorecard for ALL skills/agents/commands. Dimensions (0–10): core-fit (alignment vs its subsystem SoT — for any doc/stale-improvement asset the SoT is doc-management's 3-layer model), uniqueness (capability nothing else in the plugin provides), evidence (real usage / tests / incident provenance), cost (context+maintenance load, inverted). Verdict per asset: CORE / INTEGRATE(→named target) / KEEP-niche / REMOVE. Hard rule: an asset that duplicates a doc-management mode with no unique capability = REMOVE (not merge). Uncertain → KEEP + flagged for CEO. Full scorecard table is a required deliverable.

**Doc-core supremacy (re-judges round-1 leniency):** vault-builder's repo-doc quality machinery is a stale-doc-improvement system → judged against doc-management: drift trio (drift-fixer/gap-filler/orphan-pruner) duplicate MAINTAIN/AUDIT → expected REMOVE; docs-worker/docs-verifier duplicate REBUILD authoring + dual-review → expected REMOVE; content-fact-checker/adversarial-auditor duplicate AUDIT + dual-review → REMOVE unless scorecard shows unique NotebookLM-vault-only value (usage evidence: PickL 0 runs, ga4 1 run — weak). Export layer (Obsidian/NotebookLM/bases/canvas) = the only non-duplicate — stays. Whatever survives gets the function-group merge below; the 26→~9 table is the CEILING, scorecard may cut deeper:

| Target | Now | After | Method |
|---|---|---|---|
| vault agents | 26 | ~9 | function-group merges: drift trio→`vault-drift-fixer` · edge ×4→`vault-edge-curator` · density/orphan-link/backlinks/cross-vault/hot-cache→`vault-graph-enricher` · concept ×2 + adr ×2→`vault-knowledge-author` · stub ×2 + community-labeler + cross-cat-prefixer + bases-creator→`vault-structure-curator` · keep: vault-pm-orchestrator, docs-worker, docs-verifier, content-fact-checker, adversarial-auditor. Rubric dim→worker maps updated in the same change. |
| vault commands | 10 | ~4 | vault-build (+resume/restructure flags) · vault-score (+audit/content-verify modes) · vault-dashboard · vault-selftest; delete nbm-to-obsidian (self-described legacy alias) |
| swarm skills | 6 | 2 | `swarm` (init/start/status/stop/ticket unified) + `swarm-bench`; 3 swarm agents stay (distinct roles) |
| harness commands | 8 | 2 | `/harness <plan\|build\|qa>` + `/harness-ops <setup\|drift\|loop\|score\|verify>` — thin arg routing |
| quality-loop command | 1 | 0 | pure alias; skill triggers cover it |
| goal-{scout,judge,worker} | in plugin | revert to ~/.claude | they serve the EXTERNAL goalbuddy skill by plain-name dispatch — out of coding-system scope |

**System heart (CEO 2026-06-06): contracts + retro-memory.** Two first-class mechanisms every subsystem hangs off:

1. **Project-context resolution order (new shared contract — `agents/references/project-context-resolution.md`):** whenever any agent needs project understanding (PM PLAN ingestion, doc-management Phase-0/authoring, retro read-side, swarm-explorer, setup-harness scan), resolve in this order — ① **Obsidian vault** `~/Documents/Knowledge/wiki/projects/<repo-slug>/` (read `_graph/GRAPH_REPORT.md`, `intent/` decisions·gotchas·history, hot cache) → ② repo `graphify-out/` (graph query/explain) → ③ build code-only graph (`graphify update .`, AST-only) → ④ raw source scan (last resort). Vault hit = cheapest + carries Why; codebase = fallback, never first. Wire-in points patched in round-2: pm-orchestrator.md, doc-management SKILL.md, retro.md, swarm-explorer.md, setup-harness Step 1.
2. **Retro write contract:** lessons append-only + evidence-cited to — vault `intent/gotchas` (if vault exists) AND repo `.claude/insights.md`, with a one-line pointer into session memory. Never rewrite prior entries. This closes the loop: next run's context resolution (①) reads what retro wrote.
3. **Binding contracts inventory** (README section in round-2): ticket schema · review.json schema · scope_files hard gate · SHA-256 verify-log evidence · doc frontmatter (type/topic/source_commit/manual_edit) · goal receipts · swarm ticket schema — all code-validated, none prompt-only.
4. **Slop-free zones (Conductor/Holtz 2026-06, adopted):** NEW hook `pre-edit-human-only.sh` — denies AI Edit/Write on (a) paths listed in repo `.claude/human-only.paths`, (b) files containing a `HUMAN-ONLY` marker line. Tier-2 protected core: `schemas/`, `hooks/guard-*`, governance SoT pages — editable only with `AUTO_PILOT_ALLOW_CORE_EDIT=1` + mandatory review. Rationale: AI reading slop reproduces slop; human-crafted core contracts stay human. Docs side already covered by `manual_edit: true` frontmatter. Plus CLAUDE.md principle line: prompts/specs are the durable re-runnable asset; code is the output ("code is sawdust").
5. **Round-1 review gap-closers (from honest self-assessment):** F6 core-loop E2E smoke MANDATORY in functional QA (explicit timeout; skip requires written reason + compensating dispatch smoke) · scorecard rounds ≥1 cross-scored by both reviewers (not author-only) · post-consolidation vault agent-dispatch smoke 1회 · doc-management MAINTAIN fixture eval 1건.

**Loop contract (체계화):** repeat rounds of [CONSOLIDATE/OPTIMIZE → functional QA (F1–F6: hook stdin cases, discovery, script smokes incl. freshness fixtures + vault selftest + MCP boot, full suites, quality-eval 13-dim honest score, eval smoke) → skill-reviewer pass → dual adversarial review] until BOTH reviewers APPROVE with zero new findings; cap 4 rounds then honest stop-report. Every merge passes a zero-capability-loss diff check (old content coverage mapped into new home). Each round = logical commits. Self-assessment never claims perfection — residual risks always listed.

- vault Python path move: import breakage risk — gated by running vault tests post-move.
- Reviewer-pair "merge" is checklist extraction, not file fusion — file fusion would break tested dispatch-by-name; this is the deepest safe dedup.
- swarm untested for 3 weeks — selftest after move, not full e2e.
- Hook symlink behavior (settings.json → symlink) verified at tail, fallback = 1-line wrapper.
- Agent count 46+ in one plugin: same as today's total across plugins; no net context increase.
- claim-ledger retirement: PickL-API's live ledger instance untouched this round (its repo's clean-slate track retires it separately); the PATTERN is simply not carried into the plugin.
- Renames (doc-management, swarm): old trigger phrases preserved in descriptions, but external docs/memory referencing old skill names go stale until tail cleanup.

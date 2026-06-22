---
type: plan
topic: auto-pilot-master-plan
source_commit: 52776f7440fe2dd2bf472784717549be258b7c75
manual_edit: true
---

# auto-pilot — master plan & status

> **Single context entry point.** Read this first to grasp purpose, what's done, what's next.
> Loop design detail: [`architecture.md`](architecture.md). Per-change design specs: [`specs/`](specs/).

---

## 1. Purpose

> Identity has two distinct levels — keep them separate. Canonical terms: `CONTEXT.md`.

**auto-pilot plugin** = a Claude Code **brownfield development toolkit**, built on an
Obsidian **vault** as its knowledge substrate. A continuous autoresearch loop keeps
the vault stocked with verified external knowledge (library docs via context7, web,
YouTube, dev/LLM communities); the dev loop runs on top of it, injecting the best
context in and writing what it learns — including its mistakes and the installed
project's conversation history — back out.

**auto-pilot loop** = the flagship, single-purpose engine inside the plugin: drives
**spec-based feature / refactor / bugfix work on an EXISTING codebase to merged**, by
**integrating the existing Claude Code skill ecosystem** into each loop stage.

- **Target: brownfield only.** Existing repo with code, tests, conventions. Examples: "add OAuth to auth", "refactor payments", "fix these P1 bugs".
- **The loop is single-mode** — NOT greenfield, NOT a standalone quality-eval scorer. (The 2026-05-29 decision dropped the multi-*mode* loop idea; that is about the loop, not the plugin, which legitimately bundles many standalone tools.)
- **The novelty:** the PM→Worker→Review→Verify→Commit backbone does not reimplement each stage — it **delegates to a best-in-class skill** where one exists. auto-pilot is the orchestration glue + the safety guards (hooks, sandbox, contract layer) that let those skills run unattended.

Why brownfield: every friction guard presupposes existing code (composition-root breakage, scope-drift REJECT, source-first debug, worktree + atomic merge to `$ROOT`). Born from 381-session `/insights` friction — all existing-project maintenance accidents.

**Decision record — vault-as-substrate reframe (2026-06-14):** the prior "single
brownfield loop" purpose under-described the project and conflicted with two other
purpose statements (architecture.md's 4-pillar table, CONTEXT.md's old Hermes title).
Resolved: the **plugin** is a vault-grounded toolkit, the **vault** is the foundation,
the **loop** stays single-mode. Approach: cherry-pick concepts from ruflo
(GOAP-style deterministic-plan-then-escalate, retrieval memory) — reject its heavy
infra (vector DB, consensus, federation) until evidence demands it. The first increment was
the **closed learning loop** (mistakes + conversation history → vault → injected back
at dispatch); its class-nudge injection was **removed 2026-06-20** as a measured no-op
(learning-loop design docs removed 2026-06-22).

Increments 2 & 3 decisions are locked but not yet phase-specced (designed after
increment 1 produces data) — see `docs/adr/0003-gated-ondemand-enrich-two-tier-escalation.md`:
- **Increment 2 (enrich):** on-demand targeted (not continuous); gate = deterministic
  source-tier floor + evidence persistence (snippet+URL+date+SHA), LLM-judge advisory
  only; source order context7 → web → community.
- **Increment 3 (2-tier loop):** typed escalation records
  (`{problem_class, tried, evidence, suggested_enrich_query}`) mark the tier-1→tier-2
  boundary; that record is also increment 2's enrichment trigger (the two share one seam).
  **Phase-specced + shipped 2026-06-15** (deterministic core; details in `docs/architecture.md` §Vault enrichment + typed escalation).

> **Scope note (2026-05-29):** a brief mid-session idea to make auto-pilot a multi-mode "build/review/perfect" platform was **dropped**. The skill/hook → plugin packaging & management concern moved to a **separate new project, `plugin-forge`** (a plugin generator that composes managed plugins from the user's existing hand-made skills/hooks). auto-pilot stays build-only and is simply one of the plugins `plugin-forge` will manage.

## 2. Skill integration map

Each loop stage routes to a skill/agent. This is the "system that integrates various skills" view.

| Loop stage | Integrated skill / agent | Status |
|---|---|---|
| Context / code map | **graphify** (`graphify-out/`) | 🔜 deferred → after live loop (see §5) |
| Pre-dispatch scope gate | `tech-critic-lead` (internal agent) | ✅ built |
| Implementation | `worker` subagent (Sonnet 4.6, 1M) | ✅ built |
| Adversarial review | `codex` + cold `claude` reviewers | ✅ built |
| TDD / security gates | `review-gatekeeper` (`tdd-gate` + `security` modes) | ✅ built |
| Verify / scoring | project verify cmds (+ `adversarial-review-loop` codebase mode, optional — DECIDED 2026-06-13: deferred until G1, see §6) | ✅ / 🔜 |
| Doc sync | `doc-management` (MAINTAIN/AUDIT modes) | 🔜 planned |
| Progress / decisions log | `PROGRESS.md` + `decisions.md` writer | 🔜 (Q2) |

## 3. What it is (structure)

A **plugin** (container) bundling: skills, commands, agents, hooks, schemas, Python helpers. Why a plugin and not a lone skill: **hooks cannot ship inside a skill**, and the friction guards are hook-only. Layout: see project `CLAUDE.md`.

Runtime roles (easy to confuse):
- **PM** = the main Opus session itself, reading `agents/pm-orchestrator.md` as its contract. **Never dispatched as a subagent.**
- **Workers** = dispatched via the `Agent` tool; **reviewers** = hardened reviewer agents, with `scripts/_reviewer_wrapper.py` used for parallel `claude -p` subprocess dispatch when env isolation is required. PM contract is the SoT.

## 4. Progress

Core loop built + dogfooded green; the plugin is **currently disabled** (not under active development).

- **Built (PR1–PR5, merged):** schema-validated PM-signed contract layer; worktree lifecycle + merge-conflict state machine; 4-layer reviewer sandbox; state lock + crash-safe resume + cost cap + dogfood gates. Reviewer roles aligned to the live set (`codex-reviewer` / `claude-reviewer` / `review-gatekeeper` + worker/critic); failure recovery uses recoverable `stash_if_dirty`, never destructive root resets.
- **Proven live (self-dogfood, 2026-06-10/12):** full bare e2e (commit `f4a2f59`); reviewer REJECT→fix→APPROVE (run-4 ph1); merge-conflict recovery + parallel multi-contract dispatch (run-4 ph2, PR #32); multi-phase advance (run-3). Discovery seam + graphify-context bundling (Steps 1–2) wired and proven on the 2nd live run. Step/break detail lives in git history + `architecture.md`.
- **Honest gaps:** loop logic is PM markdown — no deterministic e2e test of the dispatch/gate flow. **Zero external-repo run** — every proof is on this repo itself. First brownfield run on a non-owned repo (**G1**, target TBD) is the open milestone; Step-3 relevance digest stays deferred-until-G1-data.

## 5. Current work

Plugin disabled — no active work. The single open milestone is **G1** (first external brownfield run); everything below it is measured-deferred.

## 6. Resolved decisions

**Fatal (resolved by the 2026-05-29 resequence):** SHA-pin the *copied report bytes*, not the graph (graphify's LLM semantic layer is non-reproducible — record the graph by provenance only); copy needed context into `context-bundle/` because `graphify-out/` is unreachable from worktrees; prove the loop live before layering graphify.

**Decision records:**
- **Q4 verify integration (2026-06-13):** verify stays project test/lint/typecheck/build only; `adversarial-review-loop` codebase mode as a verify-stage scorer is deferred until G1 shows a gap. "Measure before optimizing."
- **Review delegation (2026-06-13):** keep the internal hardened reviewer pair (proven across 4 live runs incl. REJECT→fix + evidence-gate enforcement); revisit only if reviewer contracts diverge from `skills/adversarial-review-loop/references/review-core.md` (the shared review-substance SoT).

## 7. Cost model
- **Interactive subscription (this user):** token $ is irrelevant — global rule is *speed > token cost*. graphify regen is gated on latency + redundancy only, never $.
- **API-billed headless (other users):** `headless-loop.py --max-cost-usd` is a real $ guard. **graphify token spend must count against this cap** — and if `GEMINI_API_KEY`/`GOOGLE_API_KEY` is unset, graphify falls back to dispatching Claude subagents from the host session (nested dispatch under `--dangerously-skip-permissions`). Headless path should set a Gemini key so extraction doesn't recurse, and the cap must account for graphify's burn.

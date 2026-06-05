---
name: codebase-perfection-loop
description: "DEPRECATED (2026-06-05) — superseded by `adversarial-review-loop` (codebase mode: 13-dim rubric + parallel contract fan-out) and `pm-quality-harness-loop` (full quality→ship lifecycle). Retained only for its tmux 10-worker launcher + reference rubrics. Do NOT auto-trigger on generic quality phrases; invoke ONLY on explicit \"/codebase-perfection-loop\" or \"codebase perfection loop\". For codebase quality use adversarial-review-loop; for quality→ship use pm-quality-harness-loop."
---

# Codebase Perfection Loop

> **DEPRECATED (2026-06-05).** Superseded by `adversarial-review-loop` (codebase mode —
> 13-dim rubric + parallel contract fan-out) and `pm-quality-harness-loop` (full
> quality→ship lifecycle). This skill is kept only for its tmux 10-worker launcher
> (`scripts/tmux-launcher.sh`) and reference rubrics (`references/`). Prefer the
> successors for new work; do not trigger this on generic quality phrasing.

Drive a codebase toward big-tech 95+ quality with a repeatable, multi-agent loop. The methodology is the artifact — apply it to any project, any language, any size.

## Core philosophy

**Speed > token cost.** Independent work goes parallel. The user's bottleneck is wall-clock, not API spend.

**Verify before claim.** Memory, PR descriptions, and "resolved" labels lie. Every claim about current state requires a fresh grep / read / smoke check before acting on it.

**Deep modules, thin interfaces.** Prefer one 600-line cohesive module over five 120-line wrappers. Module size limits are a guardrail, not a goal. Splitting purely to pass `wc -l < 500` is an anti-pattern.

**Repo self-containment.** Anything an AI or new engineer needs to understand the system lives inside the repo, not in an external vault or wiki they may not have. The `.claude/` tree is the SoT.

**1-person / small-team context.** No feature flags for "future flexibility", no multi-region scaffolding for a single EC2, no Kubernetes manifests for a t3.medium. Match abstraction to real headcount and infra.

## When to use

- "전체 코드베이스 분석하고 95+ 만들어" / "perfect this codebase" / "deep audit + improve"
- After a major feature ships and the codebase has accumulated drift
- Onboarding a new project — establish baseline + harness in one pass
- Periodic quality cycle (quarterly, post-incident)

Do NOT use for:
- Single-bug fix (use `debugging` / `systematic-debugging`)
- Single PR review (use `adversarial-review-loop`)
- Greenfield design (use `brainstorming` / `office-hours`)

## The loop

```
Phase 0  Bootstrap        — snapshot current state
Phase 1  Parallel Audit   — 10 workers, non-overlapping scopes
Phase 2  Synthesis        — PM matrix + prioritized gaps
Phase 3  Approval Gate    — 3 decisions from user
Phase 4  Code Fixes (A)   — parallel implementers per ticket
Phase 5  Docs Rewrite (B) — parallel rewriters per .claude/ subtree
Phase 6  Re-score         — confirm 95+ or loop back to Phase 1
```

Each phase has a checklist. Treat them as TaskCreate items so progress is visible.

---

## Phase 0 — Bootstrap

Before launching any worker:

1. **Confirm scope.** Repo path, primary language, infra context (solo dev / team / scale). 1 question max. Default: current working directory, language auto-detect, single-EC2 1-dev unless told otherwise.
2. **Snapshot state.** `git status` (warn on uncommitted), `git log --oneline -10`, total LOC, file count. Save mental model.
3. **Locate existing baselines.** `find . -maxdepth 3 -name CLAUDE.md`, `ls docs/ .claude/ 2>/dev/null`. Note what already exists; do not duplicate.

If uncommitted changes block work, surface to user before proceeding.

---

## Phase 1 — Parallel Audit (10 workers)

Launch all 10 in **one message** with multiple `Agent` tool blocks. Background mode (`run_in_background: true`) for all. The PM (you) sleeps until at least 6 complete, then can begin synthesis on completed ones.

**Worker scope assignment.** Read `references/worker-scopes.md` for the full prompt template per worker. The 10 workers cover orthogonal dimensions:

| # | Worker | Agent type | Scope |
|---|--------|------------|-------|
| W1 | Code size / dead code | `Explore` | files >threshold, dead symbols, duplication hotspots, test gaps |
| W2 | Docs inventory | `Explore` | all .md files, deletion candidates, wiki-tree violations |
| W3 | Architecture / interface depth | `Plan` | layer boundaries, deep vs shallow, abstraction justification, AI-nav |
| W4 | Adversarial general | `codex:codex-rescue` | hidden complexity, type-safety reality, test false-safety, band-aid validators, hidden coupling |
| W5 | Test architecture | `Explore` | conftest sprawl, monkeypatch correctness, test sizes, skip/xfail |
| W6 | Performance / infra fit | `Plan` | RTT count, async correctness, cache patterns, DB efficiency, infra overkill |
| W7 | Adversarial domain | `codex:codex-rescue` | domain-specific (prompts/LLM, ML pipeline, frontend bundles, etc.) |
| W8 | Config / env / security | `Explore` | env var sprawl, single-source violations, secret handling, .env.example completeness |
| W9 | Git/memory drift | `general-purpose` | commit-vs-diff claims, memory-vs-code drift, TODO age |
| W10 | Public API / naming | `Plan` | `__init__` re-exports, public/private boundaries, CLI dead options, naming consistency, shallow modules |

**Critical**: each worker's prompt must be self-contained (no shared context) AND must declare what other workers cover, telling it "don't duplicate — focus on X only". This prevents 10x token waste from overlap.

**Output contract**: every worker returns markdown in a prescribed format (table + bulleted findings + numeric verdict 0–100 if applicable). The synthesis step depends on this contract.

---

## Phase 2 — Synthesis Matrix

Once 8+ workers complete, assemble a scoring matrix:

```
| Dim | Score | Critical findings |
|---|---|---|
| Surface API | 42 | private boundary meaningless, dead CLI flags... |
| Type safety | 70 | Any leak 1669, type:ignore 102... |
| ... | ... | ... |
```

**Compute composite estimate**: weighted average. Default weights — surface 1.5×, AI-nav 1.5×, layer boundaries 1×, perf 1×, others 1×. Big-tech 95+ requires every cell ≥ 85.

**Prioritize gaps**:
- **P0** = cells <60 OR contract violations (schema-prompt mismatch, layer-boundary breach)
- **P1** = cells 60–80 OR justified-but-suspect abstractions
- **P2** = cells 80–90 OR cleanup wins

Present matrix + top 8–12 gaps to user in <30 lines. Do not dump worker reports — the user reads the synthesis.

---

## Phase 3 — Approval Gate

Use `AskUserQuestion` for 3 decisions. These shape the entire Phase 4/5 plan, so don't skip:

1. **External-vault policy** — if a separate docs vault (Obsidian, Notion, wiki) exists: archive into `.claude/`, mirror, or keep as SoT?
2. **PR strategy** — single mega-PR, phased (A→B with multiple PRs each), or P0-only first?
3. **Existing docs disposition** — delete all, archive, or selective preservation?

Default recommendations (mark "Recommended"):
- Archive vault into `.claude/` (repo self-containment)
- Phased A→B with multiple PRs each (review fits human window)
- Delete all (clean slate; new wiki-tree replaces)

Memo decisions to TaskCreate; they constrain all later tickets.

---

## Phase 4 — Code Fixes (Parallel)

Convert each P0 + P1 gap into a **self-contained ticket**. Ticket schema:

```yaml
id: T-NN
title: short imperative
scope_files: [list]      # touch only these
out_of_scope_files: [...] # explicitly do NOT touch
why: 1-line user-criterion link
acceptance:
  - test command exits 0
  - grep proves removal/addition
  - module size ≤ N
parallel_safe: true|false  # false if conflicts with another open ticket
```

**Dispatch rules**:
- Independent tickets (no scope_files overlap) → parallel via multiple `Agent` blocks in one message.
- Sequential tickets (overlap or T-B depends on T-A) → run after dependencies; declare via `depends_on:` field.
- Each ticket runs in its own worktree if branch isolation matters: invoke `superpowers:using-git-worktrees`.

**Per-ticket workflow** (executor agent follows):
1. Read scope files; confirm they exist.
2. Implement smallest possible change satisfying acceptance criteria.
3. Run project's test command (auto-detect: `pytest -x`, `npm test`, `cargo test`, `go test ./...`).
4. Run formatter + linter.
5. Commit with conventional commit format. Do NOT push.
6. Report: files changed, LOC delta, tests passing, acceptance verified.

**PM (you) verify** each ticket's report before considering it done. Don't trust agent claims — `git diff --stat` and rerun the acceptance test.

---

## Phase 5 — Docs Rewrite (Parallel) — Wiki-Tree Harness

Apply the structure from `references/wiki-tree-harness.md`. Summary:

```
.claude/
├── rules/          # forbidden actions, deployment safety, verification methodology
├── architecture/   # system overview, pipeline, layer rules, deep-module spec
├── runbooks/       # incident response per failure mode
├── branding/       # project identity, scale context, anti-overengineering doctrine
└── prompts/        # LLM prompt rules (if applicable to project)

CLAUDE.md           # ≤80 lines, index pointing to .claude/ subtrees
README.md           # ≤100 lines, user-facing entry
docs/               # DELETE or minimal (auto-generated module ref only, gitignored)
src/**/CLAUDE.md    # 20-40 line self-contained module overview, NO external vault redirect
```

**Wiki-tree rule**: top-level docs are abstract + concise. Each link leads to a subfolder with detail. Detail in subfolder leads to deeper subfolder if needed. Max depth 3.

**Dispatch parallel rewriters** (5 workers, one per `.claude/` subtree):
- W-rules: `.claude/rules/*.md`
- W-arch: `.claude/architecture/*.md`
- W-runbooks: `.claude/runbooks/*.md`
- W-branding: `.claude/branding/*.md`
- W-prompts: `.claude/prompts/*.md` (skip if not applicable)

Plus 2 more:
- W-index: root `CLAUDE.md`, `README.md`, module-level `CLAUDE.md` stubs
- W-cleanup: delete `docs/`, `.planning/`, generated artifacts; add `.gitignore` entries

Each rewriter receives:
- Phase 2 synthesis (full)
- List of files it owns
- "Reference but rewrite from scratch" rule — read existing docs, extract durable truths, discard procedural cruft
- Output style guide: section structure, max page length, link format

**Verify**: after all rewriters complete, run a link check (every `[text](path)` resolves, every `[[name]]` resolves to a file in the new tree). Fix broken links before declaring done.

---

## Phase 6 — Re-score

Re-launch a subset of Phase 1 workers (W1, W3, W4, W10) on the new state. Compare against Phase 2 matrix. If every cell ≥ 85 → done. Else identify residual gaps, optionally loop Phase 4/5 for them.

**Stop criteria**: composite ≥ 95 OR user signs off OR diminishing returns (2 loops without ≥3-point gain).

---

## Anti-patterns the loop prevents

| Anti-pattern | How the loop kills it |
|---|---|
| "Memory says X exists" claim acted on without verifying | W9 drift check; ticket acceptance criteria require grep proof |
| Splitting a module purely to pass size lint | W3 + W10 flag shallow modules; PM verdict treats artificial split as gap |
| Validator band-aid for LLM output | W7 (domain adversarial) explicitly looks for post-hoc regex/numeric fixes |
| 100s of `.md` files of mixed staleness | W2 inventory + Phase 5 W-cleanup deletes; new tree caps at known structure |
| Doc rewrite that just shuffles old text | Phase 5 "reference but rewrite from scratch" + style guide forces re-derivation |
| 1-person codebase with K8s manifests | W6 calls out infra overkill; branding/ doc encodes anti-overengineering as doctrine |

---

## Resource references

Read these only when you reach the phase that needs them:

- `references/worker-scopes.md` — full prompt template for each of W1–W10
- `references/wiki-tree-harness.md` — exact `.claude/` subtree contents + page templates
- `references/big-tech-rubric.md` — scoring rubric per dimension (PASS/CONCERN/FAIL thresholds)
- `references/synthesis-matrix.md` — PM verdict format + weighting formula
- `references/ticket-schema.md` — Phase 4 ticket format with examples

## Cross-language notes

The methodology is language-agnostic. Per-language tweaks:

- **Python**: `wc -l`, `vulture`, `ruff`, `pytest`, `mypy`, `pip-audit`. Size threshold 500.
- **TypeScript/JS**: `wc -l`, `ts-prune`, `eslint`, `jest`/`vitest`, `tsc --noEmit`. Size threshold 400 (denser).
- **Go**: `gocyclo`, `staticcheck`, `go test ./...`, `gofmt`. Size threshold 600 (Go files trend bigger by convention).
- **Rust**: `cargo clippy`, `cargo test`, `cargo bloat`. Size threshold 500.
- **Java/Kotlin**: `detekt`/`ktlint`, JUnit, `jdeps`. Size threshold 400.

The worker scopes in `references/worker-scopes.md` have per-language Bash snippets.

## Failure modes

- **Worker returns 0 findings** — likely scope misunderstanding; re-dispatch with sharper scope statement.
- **Conflicting findings between W3 (Plan) and W4 (Codex adversarial)** — keep both. Adversarial is by design more pessimistic. PM picks middle ground in synthesis.
- **User declines Phase 3 (approval)** — accept; Phase 4/5 don't run. Skill output is the Phase 2 verdict.
- **Phase 6 re-score regresses** — find the offending ticket via git bisect of Phase 4 commits; revert, re-plan, retry.

## After the loop

Update project memory (auto-memory or CLAUDE.md hierarchy) with:
- Final composite score
- Last loop date
- Open P2 gaps deferred
- New `.claude/` tree structure (so future agents know where SoT lives)

Do NOT commit a "score history" file in the repo unless the user asks — it ages poorly.

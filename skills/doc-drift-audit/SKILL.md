---
name: doc-drift-audit
description: >
  Audit and fix STALE project documentation + source comments so they match the
  CURRENT code, then install a guard so they can't silently drift again. Use this
  proactively whenever docs or comments are out of date, wrong, or describe
  removed/renamed behavior — e.g. "문서 최신화", "doc drift", "docs audit",
  "주석이 옛날 정책", "docs don't reflect the code", "the README/CLAUDE.md still
  describes the old X", "주석이 코드랑 안 맞아", "sync docs to the codebase",
  "update all docs to the current code", or right after a large refactor / rename /
  migration that likely staled docs + comments. Runs a parallel read-only audit
  (one agent per change-area) → ranked P0/P1/P2 findings → approval gate → fix
  (skipping dated/historical docs) → bundled deterministic CI guard. Distinguishes
  stale-as-current (must fix) from correct-historical notes (leave). Language-agnostic.
  NOT for: bootstrapping a brand-new harness / CLAUDE.md / hooks from scratch (that's
  setup-harness), exporting docs to an Obsidian/NotebookLM vault (vault-builder),
  general code-quality scoring (quality-loop / adversarial-review), or DB-schema /
  env-config drift — this skill is specifically doc↔code (and comment↔code) drift.
---

# Doc Drift Audit

Two classes of drift, two tools. Neither alone is enough:

| Class | Example | Tool | Coverage |
|-------|---------|------|----------|
| **Mechanical** | dead path ref, `file:NNN` past EOF, retired symbol named as current | **deterministic hook** (regex/AST, CI-gated) | 100% on this class |
| **Semantic** | prose describes logic that changed; comment lies about behavior | **LLM fan-out audit** (this skill) | high, not perfect |

Be honest about the ceiling: there is no "perfect/automatic 100%". The hook makes mechanical drift unmergeable; the audit makes semantic drift cheap to catch. Prevention (same-PR doc update) is the global Hard Rule that reduces what enters.

## Step 0 — Scope (ask if unclear)

Drift surface is usually large. Pick scope before fanning out:
- **Change-driven (default)** — audit only docs/comments covering code that changed since the last audit (recent PRs, refactors). Targeted, fast.
- **Full sweep** — all docs + all source comments vs code. Thorough, expensive.
- **Comments-first** — only misleading source comments (fastest single win).

Use `git log`, recent PR titles, and any handoff/memory notes to build the change-list. Establish ground truth cheaply first: grep for known-retired terms, list the actual files/exports that the docs reference.

## Step 1 — Drift map (parallel, READ-ONLY)

Dispatch N parallel agents (`Agent`, subagent_type `general-purpose`), **one per change-area** (e.g. auth, data layer, a refactored module, folder-level CLAUDE.md, source comments). Read-only ⇒ no worktree needed, zero conflict, cheap.

Each agent prompt MUST include:
- **Known recent changes** to verify against current code (give the facts you have).
- **Exact scope**: which doc files + which source dirs' comments.
- **Classification rule**:
  - `STALE-AS-CURRENT` (BAD) — describes a removed/changed mechanism as if current.
  - `CORRECT-HISTORICAL` (OK, leave) — explicitly notes the removal ("legacy X retired in #N").
  - `CORRECT-CURRENT` (OK).
- **Verify every claim against real code** (grep + read), cite evidence `file:line`. Grep alone cannot tell stale from historical — the agent must read.
- **Structured output**: a table `| # | file:line | claim (quote) | code reality (evidence file:line) | severity P0/P1/P2 | proposed fix |`, plus per-severity counts and an explicit list of CORRECT items to NOT touch.

Copy-paste auditor prompt template (one per area — fill the `<…>` slots):

```
READ-ONLY doc-drift audit. Do NOT edit/write any file. Final message = findings only.

Project: <one-line stack>. Repo root: <abs path>

KNOWN RECENT CHANGES to verify against current code:
- <fact 1 — e.g. "X was removed in PR #N; replaced by Y". VERIFY in code (grep for X).>
- <fact 2 …>

YOUR SCOPE:
- Doc files: <explicit list>
- Source comments in: <dirs/globs> mentioning <relevant symbols/terms>

TASK: For each doc claim OR source comment in scope, READ the current code it
describes and classify:
- STALE-AS-CURRENT (BAD): describes a removed/changed mechanism as if current.
- CORRECT-HISTORICAL (OK, leave): explicitly notes the removal ("legacy X retired #N").
- CORRECT-CURRENT (OK).
Verify EVERY claim against real code (grep + read). Cite evidence file:line.

OUTPUT (exactly):
## <Area> drift findings
First state ground-truth you established (does X still exist? evidence file:line).
Then a table: | # | file:line | claim (quote) | code reality (evidence) | severity | proposed fix |
severity = P0 (actively misleading) / P1 (wrong, low-confusion) / P2 (minor/outdated ref).
End with per-severity counts + a list of CORRECT items to NOT touch.
```

Giving each agent the **known recent changes** is what makes this cheap and accurate — without them the agent re-discovers history from scratch and mislabels correct-historical notes as drift.

## Step 2 — Consolidate

Merge agent findings into one ranked report (dedup cross-area overlaps). Identify **root causes** — most P0/P1 usually collapse into a few (a deleted file still referenced, a renamed symbol, a demoted module). Write to `docs/audit/<YYYY-MM-DD>-doc-drift.md` if the project uses dated audits.

**Approval gate.** Present the table + root causes + counts. Get go-ahead before any write.

## Step 3 — Fix

- If purely mechanical and you hold exact diffs: single agent (N=1) edits directly, grouped commit — simplest, no worktree.
- If fanning out N≥2 writing agents: **git worktree per worker** (commit race / orphan-commit hazard). Non-overlapping doc-areas.
- **Skip dated/point-in-time docs** (ADRs, `docs/audit/*`, dated plans, embedded audit matrices). Rewriting them to current truth is revisionism — they record what was true then. Fix only living interface/contract docs + comments. Say what you skipped and why.

## Step 4 — Verify

Run the project's doc checks + re-grep the retired terms (expect 0 as-current) + lint/type-check/tests for any touched source. Confirm the CORRECT-historical items were left intact.

## Step 5 — Install the deterministic guard (durable fix)

So it can't silently re-drift. Add (or extend) a CI-gated check that fails on the mechanical class:
1. **Path resolution** — every inline `path/to/file` in contract docs must exist.
2. **Line range** — every line cited in a `file:…` anchor must be ≤ file length (catches refs into a shrunk file). The parser handles all the anchor styles real docs use: `file:NNN`, `file:NNN-MMM`, **`file:NNN,MMM,…` comma lists**, and `file:symbol` (path validated, symbol not line-checked). A naive `:(\d+)` matcher mis-reads `file.py:33,36,37` as a missing path — the bundled guard splits path-from-suffix on the file extension instead and line-checks every number.
3. **Retired symbols** — a project-supplied list of dead symbols flagged unless an adjacent line (±3) carries a historical marker (removed/retired/legacy/deleted/replaced/consolidated/구/삭제/대체/…).
4. **Baseline file** — park accepted/conditional refs (e.g. a generated output dir) so the check starts green.

**Bundled implementation:** `scripts/check-doc-reference-integrity.mjs` (in this skill dir) — project-agnostic, no deps, Node built-ins only. Copy it into the target repo's `scripts/` dir, edit the `CONFIG` block at the top (`CONTRACT_DIRS`, `CONTRACT_FILES`, `SOURCE_ROOTS`, `RETIRED_SYMBOLS`, `PATH_PREFIX`, `BASELINE_FILE`) for that repo's layout + language, and wire it into the project's doc-check / CI step. If the repo already has a doc-integrity check, prefer extending its allowlist/patterns over a second file.

Field-tested instances:
- **TS/Next**: `sportic365-web/scripts/docs/check-doc-reference-integrity.mjs`, wired into `npm run docs:check` (CI-gated) — worked example of CONFIG values + a baseline file for conditional refs.
- **Python/FastAPI**: `clai-api/scripts/docs/check-doc-reference-integrity.mjs`, wired into a `make docs-check` Makefile target + a CI step (ubuntu runners ship Node, so no `setup-node` needed). Its CONFIG sets `SOURCE_EXT = /\.py$/`, scans `src/*/CLAUDE.md` by basename, and adds `.claude/{branding,prompts}` to `CONTRACT_DIRS`. This is where the comma-anchor parser hardening came from (the repo's docs cite `file.py:33,36,37`-style multi-line anchors heavily).

## Anti-patterns

| Don't | Do |
|-------|-----|
| Global find-replace on a retired term | Read code per occurrence — some mentions are correct-historical |
| Rewrite dated ADRs/plans to "current" | Leave them; they're history. Fix living docs only |
| Trust a green narrow doc-check as "no drift" | Narrow checks have blind spots; run the semantic audit |
| Hook only, or skill only | Both — mechanical hook + periodic semantic audit |
| Claim "docs now perfect" | Report P0/P1/P2 counts + what was skipped + residual semantic risk |

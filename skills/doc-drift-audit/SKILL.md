---
name: doc-drift-audit
description: >-
  Audit and fix STALE docs + source comments to match the CURRENT code, build a
  durable evidence-backed CLAIM LEDGER of every load-bearing claim (status
  verified/partial/unknown/false + evidence file:line + verification_command +
  last_verified), then install a guard so drift can't silently return. Use for:
  "문서 최신화", "doc drift", "docs audit", "주석이 옛날 정책", "sync docs to the
  codebase", "claim ledger", after a refactor/rename/migration, or when docs may
  be aspirational or agent-written. Evidence-first parallel read-only audit (one
  agent per area) → P0/P1/P2 findings + claim ledger → approval → fix (skip
  dated/historical) → CI guard. Evidence precedence: code > tests > CLI > config >
  generated > logs > historical-as-leads. Distinguishes stale-as-current (fix)
  from correct-historical (leave). NOT for: harness bootstrap (setup-harness),
  vault export (vault-builder), quality scoring (quality-loop), or DB-schema/env
  drift — this is doc↔code drift + claim verification.
---

# Doc Drift Audit + Claim Ledger

Three classes of doc problem, three responses. None alone is enough:

| Class | Example | Tool | Coverage |
|-------|---------|------|----------|
| **Mechanical** | dead path ref, `file:NNN` past EOF, retired symbol named as current | **deterministic hook** (regex/AST, CI-gated) | 100% on this class |
| **Semantic** | prose describes logic that changed; comment lies about behavior | **LLM fan-out audit** (this skill) | high, not perfect |
| **Unverified claim** | "Supabase sink is production-ready", "CLI supports `--x`" — stated as fact, never checked against code | **durable claim ledger** (this skill) | re-verifiable by command |

Be honest about the ceiling: there is no "perfect/automatic 100%". The hook makes mechanical drift unmergeable; the audit makes semantic drift cheap to catch; the ledger turns "is this still true?" into a command you can re-run instead of trust you have to take. Prevention (same-PR doc update) is the global Hard Rule that reduces what enters.

## Core discipline — evidence over docs (read first)

A doc is a **claim**, not truth. A claim is true only when **current** evidence backs it. Rank evidence highest-first:

1. **Code** paths + interfaces
2. **Tests + fixtures** — reveal intended behavior, edge cases, real usage
3. **CLI** behavior + `--help` output
4. **Config, migrations, schemas, lockfiles**
5. **Generated artifacts** from project tools
6. **Recent verified logs / audit outputs**
7. **Historical docs** (ADRs, old plans) — **LEADS ONLY, never proof**

Hard rules:
- **Never mark a claim verified because another doc says it is true.** Verify against tiers 1-6.
- **Grep alone cannot tell stale from historical** — read the code at each occurrence.
- If the repo has a wiki / semantic tier (`docs/wiki/`, `SCHEMA.md`): wiki pages are **derived, not source**. Verify wiki claims against raw sources + code like any other doc. (Full vault export/build stays with `vault-builder` — this skill only audits truth.)

## Step 0 — Scope (ask if unclear)

Drift surface is usually large. Pick scope before fanning out:
- **Change-driven (default)** — audit docs/comments covering code that changed since the last audit (recent PRs, refactors). Targeted, fast.
- **Full sweep** — all docs + all source comments vs code. Thorough, expensive.
- **Comments-first** — only misleading source comments (fastest single win).
- **Claim-ledger refresh** — re-verify an existing `docs/audit/claim-ledger.json` against current code; flip stale `verified→false`, resolve `unknown`s. Cheapest when a ledger already exists.

**First Read** (establish ground truth before fan-out) — read whichever exist: `AGENTS.md`, `CLAUDE.md` (+ folder-level), `docs/README.md`, `docs/wiki/SCHEMA.md` / `WIKI_RULE.md`, `RUNBOOK`, the ADR index, `.claude/rules/`. Use `git log`, recent PR titles, and handoff/memory notes to build the change-list. Grep known-retired terms; list the actual files/exports the docs reference.

If project rules require a worktree, create/use one before any edit.

## Step 1 — Drift map + claim extraction (parallel, READ-ONLY)

Dispatch N parallel agents (`Agent`, subagent_type `general-purpose`), **one per change-area** (e.g. auth, data layer, a refactored module, folder-level CLAUDE.md, source comments). Read-only ⇒ no worktree needed, zero conflict, cheap. Each agent does BOTH: (a) classify drift, (b) extract load-bearing claims as ledger rows.

**Doc classification** — bucket each doc the agent touches:
- `active` — README, docs index, current runbook, CLAUDE.md
- `generated` — status pages, ledgers, graph reports (mark as generated; never hand-edit a generated output)
- `wiki` — semantic/navigation pages (derived; verify against sources)
- `historical` — ADRs, dated plans, migration notes (leave; record-of-then)

**Drift classification rule:**
- `STALE-AS-CURRENT` (BAD) — describes a removed/changed mechanism as if current.
- `CORRECT-HISTORICAL` (OK, leave) — explicitly notes the removal ("legacy X retired in #N").
- `CORRECT-CURRENT` (OK).

Each agent prompt MUST include: the **known recent changes** to verify against, the **exact scope** (doc files + source dirs' comments), the **classification rule** above, the **evidence precedence**, and a **structured output** (drift table + claim-ledger rows + per-severity counts + CORRECT-items-to-not-touch). Cite evidence `file:line` — grep alone cannot tell stale from historical, so the agent must read.

Copy-paste auditor prompt template (one per area — fill the `<…>` slots):

```
READ-ONLY doc-drift + claim audit. Do NOT edit/write any file. Final message = findings only.

Project: <one-line stack>. Repo root: <abs path>

KNOWN RECENT CHANGES to verify against current code:
- <fact 1 — e.g. "X was removed in PR #N; replaced by Y". VERIFY in code (grep for X).>
- <fact 2 …>

YOUR SCOPE:
- Doc files: <explicit list>
- Source comments in: <dirs/globs> mentioning <relevant symbols/terms>

EVIDENCE PRECEDENCE (verify highest-first; historical docs are leads, never proof):
code > tests > CLI/--help > config/migrations/schemas > generated artifacts > logs.
Never call a claim true because another doc says so.

TASK A — drift: for each doc claim OR source comment in scope, READ the current code it
describes and classify STALE-AS-CURRENT (bad) / CORRECT-HISTORICAL (leave) / CORRECT-CURRENT.
Verify EVERY claim against real code (grep + read). Cite evidence file:line.

TASK B — claims: extract every LOAD-BEARING claim (one that, if false, misleads a
reader/agent — "X is production-ready", "CLI supports --y", "sink Z is configured by default").
For each, give status verified|partial|unknown|false, the evidence (file:line / command / test),
and a verification_command if one exists.

OUTPUT (exactly):
## <Area> drift findings
First state ground-truth you established (does X still exist? evidence file:line).
Then a table: | # | file:line | claim (quote) | code reality (evidence) | severity | proposed fix |
severity = P0 (actively misleading) / P1 (wrong, low-confusion) / P2 (minor/outdated ref).
## <Area> claim ledger rows
| claim_id | claim | status | evidence (type:ref) | verification_command | confidence |
End with per-severity counts + a list of CORRECT items to NOT touch.
```

Giving each agent the **known recent changes** is what makes this cheap and accurate — without them the agent re-discovers history from scratch and mislabels correct-historical notes as drift.

## Step 2 — Consolidate + write the claim ledger

Merge agent findings into one ranked report (dedup cross-area overlaps). Identify **root causes** — most P0/P1 usually collapse into a few (a deleted file still referenced, a renamed symbol, a demoted module). Write the findings report to `docs/audit/<YYYY-MM-DD>-doc-drift.md` if the project uses dated audits.

Then **write/update the durable claim ledger** at `docs/audit/claim-ledger.json` (configurable). One row per load-bearing claim:

```json
{
  "claim_id": "stable-id",
  "claim": "Human-readable claim",
  "status": "verified|partial|unknown|false",
  "evidence": [{ "type": "file|test|command|config|generated", "ref": "path or command", "detail": "specific evidence" }],
  "verification_command": "command if applicable",
  "last_verified": "YYYY-MM-DD",
  "confidence": "high|medium|low"
}
```

Ledger rules:
- **Update by `claim_id`, do NOT rewrite the file fresh each run** — that is what preserves history + `last_verified` and makes the ledger re-verifiable over time (vs the dated drift report, which is a one-shot snapshot).
- A `false` / `partial` / `unknown` row implies either a fix (Step 3) or an explicit "unknown — needs X" carried forward.
- Mark `generated` docs as generated; never assert a claim as `verified` on the word of another doc.

**Approval gate.** Present the findings table + root causes + per-severity counts + ledger summary (n verified / partial / unknown / false, and which flipped). Get go-ahead before any write to docs.

## Step 3 — Fix

- If purely mechanical and you hold exact diffs: single agent (N=1) edits directly, grouped commit — simplest, no worktree.
- If fanning out N≥2 writing agents: **git worktree per worker** (commit race / orphan-commit hazard). Non-overlapping doc-areas.
- **Skip dated/point-in-time docs** (ADRs, `docs/audit/*`, dated plans, embedded audit matrices). Rewriting them to current truth is revisionism — they record what was true then. Fix only living interface/contract docs + comments. Say what you skipped and why.

## Step 4 — Verify

**Verification discovery first** — find the project's REAL doc/wiki gates before running anything. Check `--help` or source; **do not invent flags**. Common examples (confirm before use): `python tools/docs/check_docs.py`, `python tools/wiki/check_wiki.py`, `python tools/wiki/graph_update.py`.

Then:
- Run the project's doc checks + re-grep the retired terms (expect 0 as-current) + lint/type-check/tests for any touched source.
- **Re-run each ledger row's `verification_command`** — a row stays `verified` only if its command passes now. Update `last_verified`.
- Confirm the `CORRECT-historical` items were left intact.

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

## Final report

Report status with evidence — **never say "complete / fixed / verified" without command output**:
- branch / worktree
- files changed + docs **skipped** (and why)
- P0/P1/P2 counts + root causes
- **claim ledger**: path + counts (verified / partial / unknown / false) + which rows flipped this run
- verification commands run (+ output hash or artifact path if produced)
- residual semantic risk + unresolved unknowns
- whether merge/PR is still pending

## When NOT to use

- Bootstrapping a brand-new harness / CLAUDE.md / hooks from scratch → `setup-harness`
- Exporting docs to an Obsidian / NotebookLM vault, or building the wiki graph → `vault-builder`
- Whole-codebase quality scoring → `quality-loop` / `adversarial-review`
- DB-schema / env-config drift (not doc↔code)
- Writing a tutorial from scratch / ordinary post-ship README sync → `document-generate` / `document-release`
- Marketing copy, API-reference-only generation, graph-only generation

## Anti-patterns

| Don't | Do |
|-------|-----|
| Global find-replace on a retired term | Read code per occurrence — some mentions are correct-historical |
| Rewrite dated ADRs/plans to "current" | Leave them; they're history. Fix living docs only |
| Trust a green narrow doc-check as "no drift" | Narrow checks have blind spots; run the semantic audit |
| Mark a claim verified because another doc asserts it | Verify against code/test/CLI; cite evidence `file:line` |
| Rewrite the claim ledger fresh each run | Update by `claim_id` so history + `last_verified` survive |
| Treat wiki/generated pages as source of truth | They're derived/generated; verify against raw sources |
| Hook only, or skill only | Both — mechanical hook + periodic semantic audit + ledger |
| Claim "docs now perfect" | Report P0/P1/P2 counts + ledger status + what was skipped + residual risk |

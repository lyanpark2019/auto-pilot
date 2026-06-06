# AUDIT mode — full methodology

> Loaded by `doc-management` SKILL.md (MODE: AUDIT). Read-only evidence fan-out that
> finds semantic drift machines can't catch; fixes are delegated to MAINTAIN mode.
> (Absorbs the retired standalone `doc-drift-audit` skill. Its claim-ledger artifact is
> NOT carried — see SKILL.md "claim-ledger: retired"; load-bearing claims are verified
> here and recorded as findings, and the L3 freshness script owns staleness detection.)

## Three classes of doc problem — and which layer answers

| Class | Example | Layer | Coverage |
|-------|---------|-------|----------|
| **Mechanical** | dead path ref, `file:NNN` past EOF, retired symbol named as current | L2 deterministic guard (CI-gated) | 100% on this class |
| **Staleness** | doc's cited sources changed since `source_commit` | L3 freshness script (WARN) | deterministic, path-based |
| **Semantic** | prose describes logic that changed; comment lies about behavior; "X is production-ready" stated as fact but false | **this mode** (LLM fan-out) | high, not perfect |

Be honest about the ceiling: there is no "perfect/automatic 100%". The guard makes
mechanical drift unmergeable; freshness makes staleness visible; this mode makes
semantic drift cheap to catch. Prevention (same-PR doc update) is the global Hard Rule
that reduces what enters.

## Core discipline — evidence over docs

A doc is a **claim**, not truth. A claim is true only when **current** evidence backs
it. Rank evidence highest-first:

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
- Wiki/derived pages are **derived, not source** — verify them against raw sources +
  code like any other doc. (Vault export/build belongs to `vault-build`; this mode only
  audits truth.)

## Step 0 — Scope (ask if unclear)

Drift surface is usually large. Pick scope before fanning out:
- **Change-driven (default)** — audit docs/comments covering code that changed since
  the last audit (recent PRs, refactors). Targeted, fast.
- **Full sweep** — all docs + all source comments vs code. Thorough, expensive.
- **Comments-first** — only misleading source comments (fastest single win).

**First Read** (establish ground truth before fan-out) — read whichever exist:
`AGENTS.md`, `CLAUDE.md` (+ folder-level), `docs/README.md`, the ADR index,
`.claude/rules/`, runbooks. Use `git log`, recent PR titles, and handoff/memory notes
to build the **known-recent-changes list**. Grep known-retired terms; list the actual
files/exports the docs reference.

If project rules require a worktree, create/use one before any later edit.

## Step 1 — Drift map (parallel, READ-ONLY)

Dispatch N parallel agents (subagent_type `general-purpose`), **one per change-area**
(e.g. auth, data layer, a refactored module, folder-level CLAUDE.md, source comments).
Read-only ⇒ no worktree needed, zero conflict, cheap.

**Doc classification** — bucket each doc the agent touches:
- `active` — README, docs index, current runbook, CLAUDE.md
- `generated` — status pages, graph reports (never hand-edit a generated output)
- `wiki` — semantic/navigation pages (derived; verify against sources)
- `historical` — ADRs, dated plans, migration notes (leave; record-of-then)

**Drift classification rule:**
- `STALE-AS-CURRENT` (BAD) — describes a removed/changed mechanism as if current.
- `CORRECT-HISTORICAL` (OK, leave) — explicitly notes the removal ("legacy X retired in #N").
- `CORRECT-CURRENT` (OK).

Each agent prompt MUST include: the **known recent changes** to verify against, the
**exact scope** (doc files + source dirs' comments), the **classification rule**, the
**evidence precedence**, and a **structured output** (drift table + per-severity counts
+ CORRECT-items-to-not-touch). Giving each agent the known recent changes is what makes
this cheap and accurate — without them the agent re-discovers history from scratch and
mislabels correct-historical notes as drift.

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

EVIDENCE PRECEDENCE (verify highest-first; historical docs are leads, never proof):
code > tests > CLI/--help > config/migrations/schemas > generated artifacts > logs.
Never call a claim true because another doc says so.

TASK A — drift: for each doc claim OR source comment in scope, READ the current code it
describes and classify STALE-AS-CURRENT (bad) / CORRECT-HISTORICAL (leave) /
CORRECT-CURRENT. Verify EVERY claim against real code (grep + read). Cite evidence
file:line.

TASK B — load-bearing claims: flag every claim that, if false, misleads a reader/agent
("X is production-ready", "CLI supports --y", "sink Z is configured by default").
Verify each against tiers 1-6 and report status verified|partial|unknown|false with the
evidence (file:line / command / test). A false or unknown load-bearing claim is a
P0/P1 finding, not a footnote.

OUTPUT (exactly):
## <Area> drift findings
First state ground-truth you established (does X still exist? evidence file:line).
Then a table: | # | file:line | claim (quote) | code reality (evidence) | severity | proposed fix |
severity = P0 (actively misleading) / P1 (wrong, low-confusion) / P2 (minor/outdated ref).
End with per-severity counts + a list of CORRECT items to NOT touch.
```

## Step 2 — Consolidate + approval gate

Merge agent findings into one ranked report (dedup cross-area overlaps). Identify
**root causes** — most P0/P1 usually collapse into a few (a deleted file still
referenced, a renamed symbol, a demoted module). Write the findings report to
`docs/audit/<YYYY-MM-DD>-doc-drift.md` if the project uses dated audits.

**Approval gate.** Present the findings table + root causes + per-severity counts.
Get go-ahead before any write to docs.

## Step 3 — Fix: delegate to MAINTAIN

Approved fixes run as MAINTAIN-mode per-doc refreshes (SKILL.md "MODE: MAINTAIN"):
re-query graph → re-read source → update cites/prose → bump `source_commit` → batch
threshold rules apply (≥5 docs or governance pages ⇒ dual review).

- If purely mechanical and exact diffs are in hand: single agent edits directly,
  grouped commit — simplest, no worktree.
- If fanning out N≥2 writing agents: **git worktree per worker** (commit race /
  orphan-commit hazard). Non-overlapping doc-areas.
- **Skip dated/point-in-time docs** (ADRs, `docs/audit/*`, dated plans, embedded audit
  matrices). Rewriting them to current truth is revisionism — they record what was
  true then. Fix only living interface/contract docs + comments. Say what you skipped
  and why.

## Step 4 — Verify

**Verification discovery first** — find the project's REAL doc/wiki gates before
running anything. Check `--help` or source; **do not invent flags**.

Then:
- Run the project's doc checks + re-grep the retired terms (expect 0 as-current) +
  lint/type-check/tests for any touched source.
- Re-run the L3 freshness script — refreshed docs must drop off the STALE list.
- Confirm the `CORRECT-HISTORICAL` items were left intact.

## Step 5 — Install the deterministic L2 guard (durable fix)

So the mechanical class can't silently re-drift. Add (or extend) a CI-gated check that
fails on:
1. **Path resolution** — every inline `path/to/file` in contract docs must exist.
2. **Line range** — every line cited in a `file:…` anchor must be ≤ file length. The
   bundled parser handles all anchor styles real docs use: `file:NNN`, `file:NNN-MMM`,
   **`file:NNN,MMM,…` comma lists**, and `file:symbol` (path validated, symbol not
   line-checked). A naive `:(\d+)` matcher mis-reads `file.py:33,36,37` as a missing
   path — the bundled guard splits path-from-suffix on the file extension instead and
   line-checks every number.
3. **Retired symbols** — a project-supplied list of dead symbols flagged unless an
   adjacent line (±3) carries a historical marker
   (removed/retired/legacy/deleted/replaced/consolidated/구/삭제/대체/…).
4. **Baseline file** — park accepted/conditional refs so the check starts green.

**Bundled implementation:**
`${CLAUDE_PLUGIN_ROOT}/skills/doc-management/scripts/check-doc-reference-integrity.mjs` —
project-agnostic, no deps, Node built-ins only. Copy it into the target repo's
`scripts/` dir, edit the `CONFIG` block at the top (`CONTRACT_DIRS`, `CONTRACT_FILES`,
`SOURCE_ROOTS`, `RETIRED_SYMBOLS`, `PATH_PREFIX`, `BASELINE_FILE`) for that repo's
layout + language, and wire it into the project's doc-check / CI step. If the repo
already has a doc-integrity check, prefer extending its allowlist/patterns over a
second file.

Field-tested instances:
- **TS/Next**: `sportic365-web/scripts/docs/check-doc-reference-integrity.mjs`, wired
  into `npm run docs:check` (CI-gated) — worked example of CONFIG values + a baseline
  file for conditional refs.
- **Python/FastAPI**: `clai-api/scripts/docs/check-doc-reference-integrity.mjs`, wired
  into a `make docs-check` Makefile target + a CI step (ubuntu runners ship Node, so no
  `setup-node` needed). Its CONFIG sets `SOURCE_EXT = /\.py$/`, scans `src/*/CLAUDE.md`
  by basename, and adds `.claude/{branding,prompts}` to `CONTRACT_DIRS`. This is where
  the comma-anchor parser hardening came from.

## Final report

Report status with evidence — **never say "complete / fixed / verified" without
command output**:
- branch / worktree
- files changed + docs **skipped** (and why)
- P0/P1/P2 counts + root causes
- load-bearing claims checked: n verified / partial / unknown / false
- verification commands run (+ output hash or artifact path if produced)
- residual semantic risk + unresolved unknowns
- whether merge/PR is still pending

## When NOT to use AUDIT mode

- Tree is genuinely patchwork → REBUILD mode (Phase 0 will confirm)
- Docs just lag recent code changes → MAINTAIN mode (freshness script finds them)
- Bootstrapping a brand-new harness / CLAUDE.md / hooks → `setup-harness`
- Exporting docs to an Obsidian / NotebookLM vault → `vault-build`
- Whole-codebase quality scoring → `adversarial-review-loop`
- DB-schema / env-config drift (not doc↔code)

## Anti-patterns

| Don't | Do |
|-------|-----|
| Global find-replace on a retired term | Read code per occurrence — some mentions are correct-historical |
| Rewrite dated ADRs/plans to "current" | Leave them; they're history. Fix living docs only |
| Trust a green narrow doc-check as "no drift" | Narrow checks have blind spots; run the semantic audit |
| Mark a claim verified because another doc asserts it | Verify against code/test/CLI; cite evidence `file:line` |
| Treat wiki/generated pages as source of truth | They're derived/generated; verify against raw sources |
| Guard only, or audit only | All three layers — L2 guard + L3 freshness + periodic semantic audit |
| Reintroduce a hand-maintained claim-ledger JSON | Retired pattern — L3 freshness + this mode replace it |
| Claim "docs now perfect" | Report P0/P1/P2 counts + what was skipped + residual risk |

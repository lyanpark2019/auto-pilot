---
name: residue-audit
description: >
  Find and remove CODE RESIDUE that static linters miss — dead code, duplicate
  logic, stale comments, wrong/unused imports, orphan symbols — via a parallel,
  read-only, judgment-based audit with strict false-positive guards, then fix
  report-first. This is the SEMANTIC counterpart to mechanical CI gates
  (ruff / vulture / jscpd): the classes a hook cannot safely block on. Use when
  asked to "residue audit", "dead code purge", "find dead code", "remove dead
  code", "kill duplicates", "dedupe logic", "잔재 제거", "데드코드 정리",
  "중복 코드 찾아", "쓸모없는 코드", "안 쓰는 import 정리", "orphan code",
  "clean up leftovers", or right after a large refactor / migration / feature
  removal that likely left behind unreferenced symbols, divergent copies, and
  comments describing deleted behavior. Runs Phase 0 baseline (linters green) →
  Phase 1 parallel read-only scan (deterministic tools + agent fan-out per
  subtree, NO deletes) → ranked P0/P1/P2 findings with a 6-gate column →
  approval gate → Phase 2 batched fixes (one residue category per PR, 6-gate
  each) → optional Phase 3 (wire mechanical CI guards). Distinguishes real
  residue from false positives (fixtures, reflection-registered classes,
  dormant flag-gated subsystems, schema example dicts, re-exports). Never
  blind-deletes — any uncertain gate is REPORT-ONLY. Language-agnostic;
  Python/FastAPI examples. NOT for: doc↔code prose drift (doc-management AUDIT
  mode), whole-codebase quality scoring (quality-loop / adversarial-review),
  DB-schema / env-config drift, or bootstrapping a harness (setup-harness).
---

# Residue Audit

Two classes of residue, two tools. Neither alone is enough:

| Class | Example | Tool | Verdict |
|-------|---------|------|---------|
| **Mechanical** | unused local, commented-out block, exact-clone span, `F401` import | **deterministic gate** (ruff / vulture / jscpd, CI-gated) | safe to auto-flag |
| **Semantic** | symbol live only via reflection/string-dispatch; two copies that *diverged*; comment that lies about current behavior | **LLM fan-out audit** (this skill) | judgment — a hook can't safely block on it |

Be honest about the ceiling: there is no "perfect/automatic 100% dead-code detection". Dynamic dispatch, framework reflection, and string-form references make whole-program reachability undecidable in practice. The gates make the mechanical class unmergeable; this audit makes the semantic class cheap to surface **and safe to act on** (6-gate before any deletion). The default posture is REPORT, not DELETE.

## Core lessons (read these first — learned the hard way)

1. **Tools = signal, not ground truth.** Every candidate from vulture / jscpd / ruff / an agent MUST be re-grepped directly before it enters findings:
   `grep -rn '<symbol>' app/` **including tests** *and* `grep -rn '<symbol>' --include='*.sql'` (RPC bodies / string-dispatch reference symbols by literal name, invisible to AST tools). A tool's "unused" verdict is a hypothesis, not a fact. (memory: `feedback_agent_scan_signal_not_truth`)
2. **6-gate before ANY deletion.** All six must pass; ANY uncertain gate → REPORT ONLY, never blind-delete. Full detail + grep recipes: [`references/six-gate.md`](references/six-gate.md). (memory: prohibitions dead-code rule, `feedback_no_delete_move`)
3. **False positives are the norm, not the exception.** Fixtures consumed by name-injection, `if False:` async-gen idioms, OpenAPI `responses=` examples + Pydantic `json_schema_extra` (live schema), `__init__.py` re-exports, DI-wired dormant subsystems (flag-gated reserved APIs ≠ dead), runtime predicate builders with 0 literal grep hits. Full catalog: [`references/false-positive-catalog.md`](references/false-positive-catalog.md). (memory: `feedback_idx_scan_zero_not_unused`)
4. **Stale comment vs historical note.** A comment describing REMOVED behavior AS CURRENT = fix. A comment saying "removed in PR #N, kept because Y" = correct historical note → LEAVE it. Do not "tidy" history.
5. **diff-hygiene.** One residue category per PR, ≤300 LOC, refactor (dedup) NEVER bundled with a behavior change. De-dup must be behavior-identical; if two copies diverged (e.g. one scrubs PII, one doesn't) that's a **BUG, not a refactor** — split it out and fix the bug deliberately.
6. **Verify-before-claim + CI parity.** Run the project's canonical test invocation (e.g. `pytest -n auto`), not a bare serial subset; never claim pass without showing the command output; never bundle commit/push/PR into the same step as verification (an autofix can strip a just-added import between edits, and a bundled push fires on RED).

## Residue taxonomy (what this skill hunts)

| Category | Definition | Primary signal | Confirm with |
|----------|------------|----------------|--------------|
| **Dead code** | symbol/function/class/module with no live reachability | vulture, ruff `F811`/`F841` | 6-gate (`references/six-gate.md`) |
| **Duplicate logic** | ≥2 spans implementing the same behavior | jscpd, eyeball | behavior-identical check (§lesson 5) |
| **Stale comment** | comment describes removed/changed behavior as current | grep retired terms | read code at the line (§lesson 4) |
| **Wrong/unused import** | import unused, or imports a moved/renamed symbol | ruff `F401`, mypy | re-grep symbol incl. tests |
| **Orphan artifact** | unreferenced fixture file, config block, generated stub | grep filename/key | entry-point + reflection gates |

## Phase 0 — Baseline (linters GREEN first)

Residue hunting on a red tree is noise. Establish ground truth:

```bash
# Python/FastAPI example — substitute the project's canonical invocation
ruff check app/ && mypy app/ && pytest -n auto app/tests/
```

- If anything is red, **stop** — fix or report the red first; do not start the audit on top of failures.
- Snapshot the deterministic-tool output as the candidate seed (NOT findings yet):
  ```bash
  ruff check app/ --select F401,F811,F841,ERA001 --output-format concise
  vulture app/ --min-confidence 80          # advisory — every hit is a hypothesis
  jscpd app/ --min-tokens 50 --reporters console  # duplicate spans — hypotheses
  ```
- Record the **canonical test command** you will re-use in Phase 2 (lesson 6). For Python that is typically `pytest -n auto`, not a single file.

## Phase 1 — Parallel read-only scan (NO deletes)

Dispatch N parallel agents (`Agent`, `subagent_type="general-purpose"`), **one per source subtree** (e.g. `app/services/`, `app/repositories/`, `app/api/`, `app/core/`, `app/domain/`). Read-only ⇒ no worktree, zero conflict, cheap. Hand each agent the Phase-0 candidate seed for its subtree so it doesn't rediscover from scratch.

Each agent MUST:
- Treat every tool candidate as a **hypothesis** and re-grep it directly (lesson 1) — incl. tests and `*.sql`.
- Run the **6-gate** mentally on each dead-code candidate; record per-gate PASS/UNCERTAIN.
- Apply the **false-positive catalog** before reporting (lesson 3) — drop FPs, or report them as `FALSE-POSITIVE (keep)` with the reason.
- For comments: classify `STALE-AS-CURRENT` (fix) vs `CORRECT-HISTORICAL` (leave) by reading the code (lesson 4).
- **Write/edit nothing.** Final message = findings only.

Copy-paste auditor prompt (one per subtree — fill the `<…>` slots):

```
READ-ONLY residue audit. Do NOT edit/write/delete any file. Final message = findings only.

Project: <one-line stack>. Repo root: <abs path>. Your subtree: <dir, e.g. app/services/>

CANDIDATE SEED (hypotheses from deterministic tools — NOT ground truth):
<paste ruff F401/F811/F841 + vulture + jscpd hits scoped to this subtree>

TASK: For each candidate AND anything else suspicious in scope, classify into:
  dead-code | duplicate-logic | stale-comment | wrong/unused-import | orphan-artifact
  | FALSE-POSITIVE (keep)

RULES (mandatory):
1. Tools are signal, not truth. Re-grep EVERY symbol directly before reporting:
   grep -rn '<symbol>' <repo>/    (INCLUDE tests)
   grep -rn '<symbol>' <repo>/ --include='*.sql'   (RPC/string-dispatch by literal name)
   If a symbol has ANY live hit you can't rule out, it is NOT dead.
2. Dead-code 6-gate — record each as PASS / UNCERTAIN:
   (1) static grep = 0  (2) no dynamic import/getattr/string-dispatch
   (3) not a route/cron/CLI entry point  (4) not framework-reflection-registered
       (FastAPI route, Pydantic model/validator, pytest fixture, DI-wired)
   (5) not in __all__ / re-export  (6) full test suite would stay green
   ANY gate UNCERTAIN → severity capped at "REPORT-ONLY, do not delete".
3. False-positive catalog — DROP or mark FALSE-POSITIVE (keep) with reason:
   pytest fixtures (name-injection), `if False:` async-gen idioms, OpenAPI
   responses= examples + Pydantic json_schema_extra (live schema), __init__.py
   re-exports, DI-wired dormant/flag-gated subsystems (reserved security APIs
   like a revoke/unrevoke pair are NOT dead), runtime predicate builders
   (.eq_if()/.in_()) with 0 literal grep hits but live.
4. Comments: STALE-AS-CURRENT (describes removed behavior as current → fix) vs
   CORRECT-HISTORICAL ("removed in PR #N, kept because Y" → LEAVE). Read the code.
5. Duplicate logic: confirm the copies are BEHAVIOR-IDENTICAL. If they diverged
   (one scrubs PII, one doesn't) flag as BUG-not-refactor.

OUTPUT (exactly):
## <subtree> residue findings
First: ground-truth you established (which candidates survived re-grep; which were FPs).
Then a table:
| # | category | file:line | evidence (grep result / quote) | 6-gate status | severity |
6-gate status = "6/6 PASS" or "GATE n UNCERTAIN: <why>" or "n/a (not deletion)".
severity = P0 (live bug / divergent-copy / misleading-as-current)
         / P1 (clear residue, all gates pass, safe to remove)
         / P2 (cosmetic / low-confidence — report-only).
End with: per-category + per-severity counts, and an explicit FALSE-POSITIVE (keep) list.
```

Giving each agent the candidate seed + the FP catalog inline is what keeps this cheap and accurate — without them the agent re-derives reachability and mislabels live-via-reflection symbols as dead.

## Consolidate → Findings table → Approval gate

Merge agent outputs into one ranked report (dedup cross-subtree overlaps; a moved symbol shows up as wrong-import in one tree and dead in another — collapse to one root cause). Present:

- the unified table `| category | file:line | evidence | 6-gate status | severity |`,
- per-category + per-severity counts,
- the **FALSE-POSITIVE (keep)** list with reasons (this is a deliverable, not noise — it documents why "obvious dead code" is alive),
- the planned **PR batching** (one category per PR — see Phase 2).

If the project uses dated audits, write to `.planning/<YYYY-MM-DD>-residue-audit.md` and remove it after the fixes land (one-shot artifact; persist durable findings to an ADR/doc — see your project's planning-doc lifecycle rule).

**STOP. Approval gate.** No deletes/edits until the user approves the table. P0 live bugs (divergent copies, misleading-as-current comments) and P1 safe removals can be approved together but still ship as separate PRs.

## Phase 2 — Batched fixes (one residue category per PR, 6-gate each)

For each approved category, in its own branch + PR (lesson 5: ≤300 LOC, never mix refactor with behavior change):

1. **Re-confirm at edit time.** Re-grep the exact symbol once more (the tree may have moved since Phase 1). Walk the 6-gate (`references/six-gate.md`) — any UNCERTAIN → demote to report-only, skip the delete.
2. **Apply the minimal edit.** Dead code → delete (or **move**, never delete, if it's a misplaced live file — `feedback_no_delete_move`). Wrong import → fix the path. Stale comment → correct it (leave historical notes). Duplicate → extract a single behavior-identical helper; if copies diverged, that's a separate **bugfix** PR, not this dedup PR.
3. **Verify — separately from commit.** Run the canonical command and SHOW its output:
   ```bash
   ruff check app/ && mypy app/ && pytest -n auto app/tests/
   ```
   Do **not** chain the commit/push into this same step (lesson 6: an autofix can strip a just-added import between edits; a bundled push fires on RED). Verify first; commit only after green is shown.
4. **Then** commit (named files only — never `git add -A`), and push/PR as a distinct action.

De-dup discipline: prove behavior-identity before extracting. If the two copies differ in side-effects (logging, PII scrubbing, error handling), do NOT merge them silently — surface the divergence as a bug and decide which behavior is correct.

## Phase 3 — Wire mechanical CI guards (optional, durable)

So the mechanical class can't silently re-accumulate. Add/extend CI-gated checks — but keep judgment classes advisory (lesson: a hook can't safely block on semantic residue):

| Guard | Posture | Why |
|-------|---------|-----|
| `ruff --select ERA001` | **blocking** | commented-out code is unambiguous residue |
| `ruff --select F401,F811,F841` | **blocking** | unused import/redef/var — already deterministic |
| `vulture --min-confidence 90` | **advisory** (report, don't fail) | high false-positive rate on reflection/DI — never auto-block deletion |
| `jscpd --threshold N` | **advisory** | duplicate ≠ always wrong; some clones are intentional |
| env/config drift (`.env.example` ⊇ referenced keys; no orphan config blocks) | **blocking** | mechanical, catches removed-feature config residue |

Wire blocking guards into pre-commit / CI; emit advisory guards as a report artifact (PR comment), not a gate. If the repo already has a residue/lint gate, extend its allowlist rather than adding a second.

## Anti-patterns

| Don't | Do |
|-------|-----|
| Delete because vulture/jscpd said so | Re-grep (incl. tests + `*.sql`), run the 6-gate, then decide |
| Blind-delete a "0 grep hits" symbol | Check reflection / DI / `__all__` / entry-point first (FP catalog) |
| Merge two duplicate spans that diverged | That's a bug — split out a behavior fix, don't silently pick one |
| "Tidy" a `removed in PR #N` comment | Leave it — historical notes are correct, not residue |
| Bundle dedup + a behavior change in one PR | One residue category per PR; refactor ≠ behavior change |
| `git add -A` then commit-and-push as one step | Named files; verify green (show output) BEFORE a separate commit/push |
| Claim "all dead code removed" | Report P0/P1/P2 counts + the FALSE-POSITIVE (keep) list + residual undecidability |

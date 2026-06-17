<!-- NOT an agent. Shared review substance (single source) for:
     auto-pilot-claude-reviewer, auto-pilot-codex-reviewer (hardened pair: ticket + review.json)
     (legacy inline-prompt/text-verdict pair claude-reviewer + codex-adversarial deleted 2026-06-07 —
      both shells are now the auto-pilot-* hardened pair)
     Shells own dispatch/boot/output contracts; THIS file owns the review substance.
     Lives under skills/adversarial-review-loop/references/ (NOT agents/) because agent
     auto-discovery scans agents/ recursively — a previous agents/references/ placement
     surfaced this file as a ghost agent ("auto-pilot:references:review-core").
     Do not add YAML frontmatter; do not move back under agents/. -->

# Review Core — shared checklist, evidence discipline, severity conventions

## Posture

- **Read-only.** Never `Edit`/`Write` production files, never run git mutations (`commit/push/reset/stash/checkout/branch/merge/rebase`). Each shell defines its own enforcement walls; this rule holds regardless.
- **Independent, fresh context.** No PM session memory, no worker rapport. Independence is the point — review what the code IS, not what anyone says it is.

## Hard gates (auto-REJECT — non-negotiable)

1. **Scope drift** — the set of changed files MUST be a subset of `contract.scope_files`. Any out-of-scope file → auto-REJECT with a `scope_drift` finding. The worker must remove out-of-scope edits before re-review.
2. **Scope reduction** — did the worker silently shrink the acceptance criteria instead of fixing the implementation? Specifically: modified a test to lower its bar — loosened assertion, removed test, `it.skip`/`xtest`/`pytest.mark.skip`. If yes → auto-REJECT with a `scope_reduction` finding. This is the "Claude shrinking the contract to make verify pass" failure mode.

## Core checklist

3. **Spec compliance** — the diff implements what the spec asks for in this phase, nothing extra, nothing missing. Spec drift cuts both ways: implementing something the spec doesn't ask for is as much a finding as skipping what it demands.
4. **Verify gate** — re-run the project verify commands yourself from `contract.verify_cmds` in `$CONTRACT_DIR/contract.json` (e.g. `pnpm test`, `pytest`, `pnpm lint`, `pnpm typecheck`, `pnpm build`). Paste/record full output. If anything fails → REJECT. Also cross-check the worker's verify-log SHA-256 (§Worker verify-report cross-check below).
5. **Naming + design** — deep modules / thin interfaces, SOLID where applicable, no premature abstractions, no leaky DRY.
6. **Project-rules / CLAUDE.md compliance** — file ≤500 lines, explicit types, dead-code 6-gate honored, no admin keys in client, plus whatever the supplied CLAUDE.md excerpts demand.
7. **Production-readiness** — error paths handled at boundaries, no half-finished features, no `TODO`/`FIXME` left behind.
8. **Comments discipline** — only WHY-comments; no narrating WHAT, no "added for ticket X".
9. **Test reality** — tests actually exercise the change, not just instantiate classes.

## Adversarial lens

- **Hidden complexity** — control-flow tricks, implicit state, untested branches.
- **Type lies** — `Any`, `# type: ignore`, casts that hide real types, untyped public API.
- **Band-aid validators** — `try/except: pass`, defensive guards that mask real bugs instead of fixing them.
- **Composition-root breakage** — modified `__init__.py` re-exports / re-export drift, import cycles, side effects at module load.
- **Security** — secrets in code, PII in logs, SQL/cmd/XSS injection, missing CSRF on mutations, admin key in client bundle.
- **Test theatre** — assertions that always pass, mocked-everything, no real coverage.
- **Spec drift** — diff implements something the spec doesn't ask for, or skips what the spec demands. (Adversarial twin of §3 Spec compliance: §3 checks the diff against the spec; this lens hunts for the sneaky cases — gold-plating, silent scope swaps, "while I was here" extras.)

## Evidence discipline (anti-guess)

- Every finding MUST cite an exact `file:line` you confirmed with `Read`/`Grep` **this run**. Never guess identifiers, symbol names, or paths from memory.
- Read each changed file in full — don't trust just the diff; verify findings against the actual code.
- Any **count** you state (files touched, test cases, occurrences) must come from a command you actually ran (`git diff --name-only`, `grep -c`, `find | wc -l`) — paste the command. Never estimate or round.
- If you cannot cite a finding to real code, **DROP it**. An unverifiable finding is a false positive, and false positives cost a whole review round.
- Prefer fewer, cited findings over many speculative ones.

### Worker verify-report cross-check (evidence over trust)

Worker reports are claims, not evidence. Worker verify reports must include the SHA-256 of the full verify output log.
- When your inputs carry that report (PM-relayed, or in the contract outputs dir), recompute the hash over the worker's persisted verify log — mismatch = doctored/stale log → REJECT.
- Re-run verify yourself regardless (§4). Worker log claims PASS but your re-run fails → REJECT.
- A verify-pass claim with no hash and no log artifact you can check is unevidenced: rely solely on your own re-run and record the missing evidence as a finding (P1).

### Codex-output sanity-check (codex-backed shells)

When the verdict is produced via Codex CLI, sanity-check every codex finding against the actual code (`Read`/`Grep`) before reporting — codex hallucinates `file:line` refs. Discard any finding whose cited location does not exist, and report whether the sanity-check passed.

### Scoped re-review (round N+1)

On a re-review round your input is the PM-frozen FIX diff (fix commits since the prior
round), not the whole branch. Verify that diff against the prior round's findings —
each fixed correctly and completely — and hunt regressions **in those hunks only**.
Out-of-scope re-audit is wasted tokens; do it only if you state cause in the verdict
(e.g., a fix hunk changes a contract that out-of-scope code consumes).
(WHO reviews is the PM's `scripts/risk_assess.py` gate; WHAT you review is this clause.)
Scope policy SoT: `agents/pm-orchestrator.md` § Token-efficiency rules, rule b.

## Severity + verdict conventions

- **Verdict:** `APPROVE` | `REJECT` (reviewers); `ABSTAIN` exists only as the codex wrapper's timeout fallback — see below. A tripped hard gate (§1–2), a failing verify re-run (§4), or a verify-log hash mismatch forces REJECT.

**ABSTAIN is wrapper-emitted only.** `verdict: ABSTAIN` exists for the bounded
codex path (`scripts/codex_review_bounded.py` writes it on double
timeout/failure, with `reviewer_meta.abstain_reason`). A reviewer never
self-selects ABSTAIN: codex-side it is the wrapper's deterministic fallback;
the cold-Claude verdict is load-bearing and must be APPROVE or REJECT — the
evidence gate (`scripts/_evidence.py`) rejects a claude ABSTAIN outright.
- **Severity ladder:** `P0` (blocker — broken behavior, security, hard-gate/spec violation; must fix), `P1` (serious defect — should fix before approve), `P2` (minor / advisory).
- **Every finding carries:** severity + `file:line` + concrete issue + concrete fix.
  - Legacy shells render the markdown table `| Sev | File:Line | Issue | Fix |`.
  - Hardened shells emit `schemas/review.schema.json` findings (`severity`, `file`, `line`, `issue`, `fix`, `finding_hash`).
- **`class` (optional, controlled vocab):** tag each finding with the single closest defect class from the `schemas/review.schema.json` `findings[].class` enum — `index-out-of-bounds`, `null-deref`, `unguarded-empty-input`, `off-by-one`, `unchecked-return`, `resource-leak`, `race-condition`, `injection`, `missing-input-validation`, `incorrect-error-handling`, `type-confusion`, `scope-violation`, `missing-test`, `spec-noncompliance`, `doc-drift`, `dead-code`. **OMIT the field when none fits** — never force a class. The learning miner keys recurrence on this canonical tag (not your free `issue` wording), so a defect that recurs across runs only accumulates toward promotion when you classify it consistently. Wrong invented values are rejected by the schema; omission is always safe.
- Scope-drift results are surfaced explicitly (out-of-scope file list), scope reduction as a dedicated flag/finding — per each shell's output contract.

## Realist Check + Pre-commitment (adapted from oh-my-claudecode critic.md, MIT — appended 2026-06-07)

**Pre-commitment (before reading the diff):** predict 3-5 problem areas from the
contract/spec alone, THEN read. Activates deliberate search instead of confirmation
skimming. Record predictions in the verdict (hit/miss is signal, not score).

**Realist Check (before reporting any P0/P1):** pressure-test each candidate finding:
1. Realistic worst case — what actually happens in production, not in theory?
2. Existing mitigations — is the exposed path already defended at another layer?
3. Detection speed — would this be caught immediately (boot failure, first test run)?
Inflated severity → DOWNGRADE; survives all three → keep. Round-2 evidence: this
check killed 2 false P1s in r2 (codex sanity notes) — finding inflation costs a
whole review round, same as a false positive.

## Reviewer contract — 4 clauses (ⓗ, appended 2026-06; supersedes nothing above)

**1. Pre-mortem mandatory question**
For every new-mechanism diff, ask: "사고 후 리뷰가 요구할 deterministic guard 가 이 PR 에
있나?" A missing guard is a **FINDING** (not a suggestion). Precedents that define the
standard: `scripts/docs/check_doc_reference_integrity.py` (mechanical drift gate, CI-wired at .github/workflows/ci.yml), with the `RETIRED_SYMBOLS` denylist (dead-symbol re-introduction guard) in `skills/doc-management/scripts/check-doc-reference-integrity.mjs`.

**2. Liveness triage**
Before any fix round, verify each finding is LIVE — cross-check the defended layer (e.g.,
the service layer may already guard what the diff exposes). Single-line adversarial findings
unverified against the live path: **do not act, mark `needs-triage`**. Acting on a stale
finding wastes a review round and can introduce regressions.

**3. 판단 휴리스틱 4종 (judgment heuristics — precedent-backed)**
- **measure-before-revert** — validate performance claims empirically before reverting
  (precedent: xdist measured +29s on 2-vCPU, then reverted — not assumed).
- **experiment-before-pivot** — run the targeted fix first; pivot only after the experiment
  fails (precedent: W4 realtime bounce before rewriting the crawler→API path).
- **flag-rollback-required** — dark-ship diffs need an explicit rollback path documented;
  absence = FINDING (precedent: REALTIME_CACHE_INVALIDATION_ENABLED dark-ship).
- **reviews-may-overturn-me** — when a later review finds a prior review wrong, record
  the overturn without defensiveness (precedent: W3c-2 P1 security regression caught by
  Codex after Claude initial pass).

**4. Round budget**
Deterministic gate input: `.planning/score/findings-round-N.json`.
Rule: round 3 live findings not decreased vs round 2 → hard-stop before round 4 +
report "전략 전환 필요"; decreasing count → round 4 = final cap.
Enforcement is an orchestrator subcommand (built by contract β of this wave) — this
clause cites it; does not implement it.

## Addendum — unhashable verify claims force REJECT (evidence enforcement, 2026-06)

Appended tightening of §Worker verify-report cross-check; everything above stands except where this supersedes it. The worker hash mandate is now universal (`worker.md` hard rule: verify output → persisted log + SHA-256) and the PM pre-screens reports for it before review dispatch (`pm-orchestrator.md`). At review time:

- **Re-run verify yourself** (§4) and **recompute the hash** over the worker's persisted verify log (`shasum -a 256 <log>`); compare against the SHA-256 stated in the report.
- **Hash mismatch = REJECT** (doctored or stale log — already the rule above, restated for completeness).
- **Unhashable claim = REJECT** — a verify-pass claim with no SHA-256, or with no persisted log you can recompute against, now forces REJECT with a `missing_verify_evidence` finding. This supersedes the earlier "rely on own re-run + record P1" leniency: a hash-less report reaching review means the PM gate was bypassed, so treat the evidence chain as broken rather than degraded.

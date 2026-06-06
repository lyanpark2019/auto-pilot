<!-- NOT an agent. Shared review substance (single source) for:
     claude-reviewer, codex-adversarial (legacy pair: inline prompt + text verdict)
     auto-pilot-claude-reviewer, auto-pilot-codex-reviewer (hardened pair: ticket + review.json)
     Shells own dispatch/boot/output contracts; THIS file owns the review substance.
     Do not add YAML frontmatter — agent discovery must skip this file. -->

# Review Core — shared checklist, evidence discipline, severity conventions

## Posture

- **Read-only.** Never `Edit`/`Write` production files, never run git mutations (`commit/push/reset/stash/checkout/branch/merge/rebase`). Each shell defines its own enforcement walls; this rule holds regardless.
- **Independent, fresh context.** No PM session memory, no worker rapport. Independence is the point — review what the code IS, not what anyone says it is.

## Hard gates (auto-REJECT — non-negotiable)

1. **Scope drift** — the set of changed files MUST be a subset of `contract.scope_files`. Any out-of-scope file → auto-REJECT with a `scope_drift` finding. The worker must remove out-of-scope edits before re-review.
2. **Scope reduction** — did the worker silently shrink the acceptance criteria instead of fixing the implementation? Specifically: modified a test to lower its bar — loosened assertion, removed test, `it.skip`/`xtest`/`pytest.mark.skip`. If yes → auto-REJECT with a `scope_reduction` finding. This is the "Claude shrinking the contract to make verify pass" failure mode.

## Core checklist

3. **Spec compliance** — the diff implements what the spec asks for in this phase, nothing extra, nothing missing. Spec drift cuts both ways: implementing something the spec doesn't ask for is as much a finding as skipping what it demands.
4. **Verify gate** — re-run the project verify commands yourself (e.g. `pnpm test`, `pytest`, `pnpm lint`, `pnpm typecheck`, `pnpm build`, or the contract's `verify.sh`). Paste/record full output. If anything fails → REJECT. Also cross-check the worker's verify-log SHA-256 (§Worker verify-report cross-check below).
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

## Severity + verdict conventions

- **Verdict is binary:** `APPROVE` | `REJECT`. A tripped hard gate (§1–2), a failing verify re-run (§4), or a verify-log hash mismatch forces REJECT.
- **Severity ladder:** `P0` (blocker — broken behavior, security, hard-gate/spec violation; must fix), `P1` (serious defect — should fix before approve), `P2` (minor / advisory).
- **Every finding carries:** severity + `file:line` + concrete issue + concrete fix.
  - Legacy shells render the markdown table `| Sev | File:Line | Issue | Fix |`.
  - Hardened shells emit `schemas/review.schema.json` findings (`severity`, `file`, `line`, `issue`, `fix`, `finding_hash`).
- Scope-drift results are surfaced explicitly (out-of-scope file list), scope reduction as a dedicated flag/finding — per each shell's output contract.

## Addendum — unhashable verify claims force REJECT (evidence enforcement, 2026-06)

Appended tightening of §Worker verify-report cross-check; everything above stands except where this supersedes it. The worker hash mandate is now universal (`worker.md` hard rule: verify output → persisted log + SHA-256) and the PM pre-screens reports for it before review dispatch (`pm-orchestrator.md`). At review time:

- **Re-run verify yourself** (§4) and **recompute the hash** over the worker's persisted verify log (`shasum -a 256 <log>`); compare against the SHA-256 stated in the report.
- **Hash mismatch = REJECT** (doctored or stale log — already the rule above, restated for completeness).
- **Unhashable claim = REJECT** — a verify-pass claim with no SHA-256, or with no persisted log you can recompute against, now forces REJECT with a `missing_verify_evidence` finding. This supersedes the earlier "rely on own re-run + record P1" leniency: a hash-less report reaching review means the PM gate was bypassed, so treat the evidence chain as broken rather than degraded.

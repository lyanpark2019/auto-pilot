---
type: spec
topic: next-session-queue
manual_edit: true
---

# Next-session work queue — 2026-06-13

Active spec. Disposal: after each item executes, strike it out; dispose the whole file once all
P1–P3 items are done (retro step per `agents/retro.md`).

---

## P1 — G1: first external brownfield run

**Why:** purpose (locked 2026-05-29) is unproven outside the auto-pilot repo itself.
`docs/master-plan.md:69` — "Zero external-repo run — all proofs on the auto-pilot repo".
`docs/master-plan.md:91` — "Next milestone — first external brownfield run (G1)".

### (a) Decision input needed from user

- **Target repo** — sportic365 is the standing candidate (`~/.claude/projects/…/memory/improvement-wave-2026-06-13.md`); user must confirm or name a different repo. The repo must have existing code, tests, and conventions.
- **Spec** — user supplies a small, self-contained feature or bugfix spec (1–3 phases). First run should be modest scope to validate the full chain on foreign conventions.

### (b) Preconditions checklist

1. Clone / open the target repo in a Claude Code session.
2. Bootstrap graphify: run `/graphify` in the target repo, then
   `python3 scripts/orchestrator.py discover --record --graphify-version <v>` to write
   `graphify-provenance.json` (Step 1 record seam — `docs/master-plan.md:81`; the Step 2 bundle-copy
   seam that carries it into the contract is `docs/master-plan.md:85`).
3. PM resolves context at dispatch step 0 (`agents/pm-orchestrator.md:268`):
   `_discovery.resolve_report(repo_root, state_dir, graphify_version, scope_files)`.
   If stale/absent → regen + `--record` again; still absent → proceed context-blind (never blocks).
4. Run `scripts/pm_preflight.sh` before each phase dispatch to generate
   `.planning/auto-pilot/preflight/phase-N.json` (TTL 900 s, `dispatch-contract-gate.sh` requires it).
5. Confirm `gh auth status` is `lyanpark2019` (CLAUDE.md identity rule) before every push.

Risk_assess + dual reviewers + review-gatekeeper modes + evidence gate fire automatically
(`skills/auto-pilot/SKILL.md:51`).

### (c) Success criteria

- Worker diff merged to the TARGET repo's `main` branch.
- Evidence chain passes the exit gate (`scripts/_evidence.py:17`): `auto-pilot-claude-reviewer`
  APPROVE with `scope_check=PASS`; `auto-pilot-codex-reviewer` APPROVE or honest ABSTAIN
  (non-empty `reviewer_meta.abstain_reason`) — codex unavailability does not fail the run, a codex REJECT does.
- `retro` agent appended to `.claude/insights.md` on the target repo.
- `orchestrator.py status` shows `completed` (not `pivot-needed` or `failed`).

### (d) Failure-data value

Any gaps feed the Hermes ledger (`hooks/learning-miner-stop.sh` runs on session Stop).
Deferred decisions revisit with G1 evidence: Q4 verify integration and ARL codebase mode
(`docs/master-plan.md:119`), Step 3 relevance digest (`docs/master-plan.md:95`).

---

## P2 — 6 Hermes tickets → assets via promotion FSM

FSM + CLI shipped 2026-06-13: `scripts/_promotion.py:1`, orchestrator subcommands
`improvements-list/gate/set-state` (`scripts/_promotion.py:127`).
Ledger: `~/.claude/projects/-Users-lyan-Documents-Project-auto-pilot/improvements/`.
Run `python3 scripts/orchestrator.py improvements-list` to see current states.

First ticket already promoted (10c5a82d shellcheck → `hooks/shellcheck-on-write.sh`).

**Human-gate rule:** `user_approved` is set only on explicit user directive; the CLI records
and validates, never auto-decides (`docs/architecture.md:97`). Promotion stays human.

**FSM command sequence for each ticket:**
```
python3 scripts/orchestrator.py improvements-set-state <prefix> accepted
# implement the asset
python3 scripts/orchestrator.py improvements-set-state <prefix> implemented
python3 scripts/orchestrator.py improvements-gate <prefix> --field tests_pass --value true
python3 scripts/orchestrator.py improvements-set-state <prefix> verified
# user explicitly approves:
python3 scripts/orchestrator.py improvements-gate <prefix> --field user_approved --value true
# after PR merges and CI passes:
python3 scripts/orchestrator.py improvements-gate <prefix> --field ci_pass --value true
python3 scripts/orchestrator.py improvements-set-state <prefix> promoted
```

### Ticket: f0714c2a — fail-open (hook)

Pattern: destructive guards emit no observable warning when they fail-open on
parse/payload mismatch — silent inert instead of advisory stderr. All 6 guard hooks affected.
**Target asset:** patch each guard to `printf '[hook:…] fail-open: …\n' >&2` before `exit 0`
on the unparseable-stdin path (non-blocking, advisory only).
File: `hooks/dispatch-contract-gate.sh:46`, similar pattern in `hooks/guard-destructive.sh`.

### Ticket: 5dc13c9a — reentry (hook)

Pattern: a guard may read its own source prose as a dispatch prompt, triggering self-lock.
**Target asset:** add a reentry guard (check `AUTO_PILOT_HOOK_ACTIVE` env or source-file path
is the hook itself) at the top of each guard hook, mirroring the Stop-hook reentry pattern
(`hooks/pm_final_report.sh:14`). Non-blocking — exit 0 on detected reentry.

### Ticket: ec583cd0 — reentry (test)

Pattern: no RED-first test for the hook reentry scenario.
**Target asset:** extend `hooks/test_dispatch_contract_gate.py` with a test case
that feeds the hook's own source file path as the prompt — expect ALLOW (not BLOCK).
TDD order: write failing test first, then fix hook.

### Ticket: 0bfc7486 — silent-failure (test)

Pattern: end-to-end ledger-pollution lifecycle untested — a run that trips an error can
write phantom ledger entries that degrade the `distinct_runs` gate.
**Target asset:** add a pytest in `tests/` (or `hooks/test_learning_miner_stop.py`) that
exercises the full scan → persist → dedup cycle with a simulated corrupt `insights.jsonl`
line, verifying no phantom entry is written.

### Ticket: 138cdacd — fixture-shape (test)

Pattern: boundary variants (empty/absent/whitespace-only) not enumerated in fixture suite.
**Target asset:** extend existing parametrize tables in `hooks/test_dispatch_contract_gate.py`
or `tests/test_hooks_guards.py` with empty-string, absent-key, and whitespace-only variants
for every hook that reads JSON fields from stdin.

### Ticket: dbc42839 — dead-path-doc (doc)

Pattern: prose counts in docs point at retired/stale registry entries. Partially mitigated by
`scripts/docs/check_doc_reference_integrity.py` (file:line guard). Verify what remains:
run `python3 scripts/docs/check_doc_reference_integrity.py` and check for count-prose that
the script cannot mechanically validate (e.g., "11 dirs / 11 active" in CLAUDE.md — counts
true at write time but not re-checked by the guard). Update any stale count prose to point
at a registry query rather than a hardcoded number.

---

## P3 — 2 hook false-positive fixes (one small PR)

Both confirmed live on 2026-06-13.

### (a) dispatch-contract-gate.sh — prose-trip on contract_dir= marker

**Root cause:** `hooks/dispatch-contract-gate.sh:50` extracts `contract_dir=<word>` via bare
`grep -oE 'contract_dir=[^[:space:]]+'` from the entire prompt text. Any Agent dispatch whose
prose mentions the literal string `contract_dir=` (e.g., this spec, a planning prompt, a
doc that explains the protocol) trips the gate even when no actual contract exists at that path.
The `TICKET=*/tickets/*.json` fallback at line 66–85 is already anchored to the canonical
dispatch shape and is safe.

**Proposed fix:** check that the extracted path contains a `contract.json` before treating it
as a dispatch marker (mirrors the `TICKET=` fallback's `cand_dir/contract.json` check at
`hooks/dispatch-contract-gate.sh:77`). Alternatively anchor to `^contract_dir=` (line-start).

**TDD:** extend `hooks/test_dispatch_contract_gate.py` with a case where the
prompt prose contains `contract_dir=/some/path` but no contract file exists at that path →
expect ALLOW, not BLOCK.

### (b) branch-lock.sh — main-repo HEAD false positive inside worktrees

**Root cause:** `hooks/branch-lock.sh:59` falls back to `work_dir=$(pwd)` when `tool_input.cwd`
is absent. When a Claude Code session's working-directory (the parent process CWD) is the
main repo root (which is on branch `main`), every bare `git push` or `git commit` invocation
from a worktree session resolves `git -C <main-repo-root> branch --show-current` → `main` and
denies. Branch resolved at `hooks/branch-lock.sh:263`/`:269`; deny condition + call at `hooks/branch-lock.sh:274`.
Live workaround: `AUTO_PILOT_MAIN_OK=1` prefix.

**Proposed fix:** before using `$(pwd)` as `work_dir`, check whether CWD is inside a
`.claude/worktrees/*` path. If so, walk up to the first parent containing a `.git` file
(not directory) and use that as `work_dir` — the worktree's own HEAD rather than the parent
repo's `main`.

**TDD:** extend `hooks/test_branch_lock.py` with a test that simulates a
worktree CWD (a git worktree checked out on a non-main branch inside a parent repo on `main`)
and verifies that a bare `git push` is ALLOWED from that worktree.

---

## P4 — low-priority residuals (backlog, no urgency)

- `hooks/pm_final_report.sh:151` — report rotation (`KEEP=20`) deletes old reports but only in
  the vault/meta or planning dir; the vault-branch rotation path (switching vault export branches)
  is not exercised in any test.
- `scripts/_promotion.py` — `user_approved` gate field carries no timestamp/session context; audit trail requires git blame.
- `scripts/_promotion.py:36` — `load_tickets` fail-fast on first corrupt ticket; partial-load mode needed for `improvements-list`.
- `scripts/_promotion.py:59` — `_locked_update` lock sidecar may persist on failed mid-mutation write; verify `_improvement.ledger_lock` teardown cleans up on exception.
- `scripts/_promotion.py` — no pre-mutate schema validation; a pre-existing invalid ticket silently passes the read, then fails post-mutate with an opaque error.
- `scripts/orchestrator.py` sits 1 line under its budget cap
  (`scripts/quality/module_size_budget.txt:35`). The next substantive addition (any new
  subcommand) forces extraction; plan for it now rather than at crunch time.
- `docs/architecture.md:344` — routing-ledger v2 deferred: `schemas/contract.schema.json` carries
  no `role` or `task_class` fields, so auto-records all collapse into one
  `worker-primary/feature-multi-file` group; per-group rebalance requires hand-authored records.
- `agents/specialist-pool.md:62` — 3 Tier-2 specialists (`database-reviewer`, `infra-reviewer`,
  `prompt-reviewer`) remain "NOT YET PORTED, do not dispatch".

---

## Gates before push (run in worktree root)

```bash
python3 scripts/docs/check_doc_reference_integrity.py
python3 -m pytest tests/ -q
```

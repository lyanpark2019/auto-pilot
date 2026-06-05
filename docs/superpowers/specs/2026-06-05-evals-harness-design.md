# Design — auto-pilot Evals Harness (SP4)

> Status: DESIGN (v3, adversarially reviewed). Date: 2026-06-05.
> Source: brainstorming session. This is sub-project **SP4** of the larger
> "reliability harness" program (see [Program context](#program-context)).
> Next step after approval: `writing-plans` → implementation.

## Purpose

Measure auto-pilot's **task success rate** over a corpus of tasks with
**deterministic** success oracles, track it over time, and **detect regressions**
— the "silently dropped from 97% → 77% after a skill/prompt change" class — and
attribute drops to harness changes.

The agent-under-test is **auto-pilot itself**: a harness change (prompt edit, hook
tweak, dispatch-protocol change, skill add/remove) that makes the PM-loop complete
spec phases less often must be caught by a number, not by vibes. This is the
measuring stick for the program's "fix the harness, not the output" principle.

## Locked decisions (do not relitigate)

1. **Python core, adopt-principles only.** No TypeScript rewrite. auto-pilot is
   already a code-enforced state machine in Python (`orchestrator.py` + `_state.py`);
   the source article's "TypeScript state machine" is incidental to its being a
   Next.js project. The principle is language-agnostic and already implemented here.
2. **Deterministic success oracle only.** No LLM-judge. A run passes iff a
   deterministic check (test pass / file exists / deliverable assertion) passes.
3. **Corpus = dogfood seed + manual promote.** Seed from existing dogfood smoke
   specs; grow by manually promoting real auto-pilot runs. No auto-promote.

## Program context

This spec is one tile of a six-part reliability-harness program. The others
(NOT in this spec): SP0 swarm tmux absorption, SP1 Closer+Retro agents, SP2
Gotchas-only skill system, SP3 evidence hard-gates (SHA test-hash + Playwright
video→PR), SP5 retro→memory loop. **SP4 (this) is sequenced first** because the
others must be measured against it — without evals you ship regressions blind.

---

## Existing infrastructure reused (verified against repo)

| Asset | Role in evals | Verified |
|---|---|---|
| `scripts/orchestrator.py` (`cmd_init`, `--spec`) | parses spec → writes `state.json` (step 1 of run) | `orchestrator.py:33,293-298`; `--force` wipes a `running` state `:48-50` |
| `scripts/headless-loop.py` | non-interactive phase driver (step 2); reads `state.json`, **no `--spec`** | `headless-loop.py:260-299`; `ROOT=Path.cwd()` at import `:49` |
| `scripts/_state.py` | `.planning/auto-pilot/` is **cwd-relative** → per-case isolation lever | `_state.py:31-32`, docstring `:16-19` |
| `scripts/_dogfood_gate.py` | **harness-health** assertions (state/contracts/trailers/worktrees) — NOT task success | `_dogfood_gate.py:48-193` |
| `scripts/dogfood_tier1.sh` / `tier2.sh` | the real two-step invocation precedent | `dogfood_tier1.sh:34-35` |
| `scripts/_budget.py` | per-run cost/token caps + session usage parse (best-effort) | `_budget.py:48,110-122` |
| `docs/specs/2026-05-28-dogfood-smoke.md` | first corpus seed (2-phase, real `Verify cmd`) | smoke-spec:31,45 |
| `skills/setup-harness/evals/evals.json` | **legacy** LLM-judge eval format — see [Reconciliation](#reconciliation) | confirmed present |

**Corrected non-reuse (round-1 findings):** `headless-loop.py` has **no** `--spec`
(the loop is state-driven). `swarm-bench bench.sh` **does not exist** in this repo
(only an empty `.benchmarks/`). `_dispatch.py` is **ticket plumbing, not a fan-out
seam** (`grep -niE 'thread|pool|parallel' scripts/_dispatch.py` → 0). Eval-level
parallelism = N concurrent `headless-loop.py` subprocesses, not `_dispatch.py`.

---

## Architecture

### Two gates, never conflated

A single oracle that mixed "did the task succeed" with "is auto-pilot's plumbing
healthy" was the core round-1 defect: a worker that writes a *wrong* deliverable
while the PM plumbing is healthy would falsely PASS. Split into two **independent
hard gates**, both blocking, neither folded into the other's metric:

- **Gate 1 — Task-success RATE (new, this spec).** Statistical rate over the
  corpus. Each case's oracle asserts the *deliverable* only (producer-agnostic;
  never reads auto-pilot internals). This is the 97→77 detector.
- **Gate 2 — Harness-health (existing, kept).** `dogfood_tier1/2` continue as a
  separate binary gate: process invariants (`_dogfood_gate.py`) that passed on
  baseline must still pass. Catches the regression subclass where the deliverable
  still lands but trailers stop / worktrees leak / PM-SIGNATURE breaks. Reported
  and gated **separately** from the rate — "separate gate," not "ungated report."

> Round-2 finding (Claude NEW-1): without Gate 2 as a *gate*, plumbing regressions
> that don't move the success rate go uncaught. Resolved by keeping dogfood as a
> first-class blocking gate alongside the new rate gate.

### Per-case execution (isolation by fresh clone)

Each case+repeat runs in its **own fresh `git clone --local`** of the repo under
test (NOT a linked `git worktree`). Default = clone, because the agent-under-test's
inner `WorktreeManager` does `git worktree add` + `git am`/`rebase-apply`
(`_worktree.py:125,225-242`); nesting that inside an outer *linked* worktree shares
one gitdir/ref-namespace and collides (`StaleAmStateError`, `rebase-apply` path
clashes). A separate clone gives each case its own object store and `.planning/`.

Per case, in its clone (cwd = clone root):

```
python3 scripts/orchestrator.py init --spec <case>/spec.md --force --max-workers K_w
python3 scripts/headless-loop.py --max-iter M --max-cost-usd C   # reads state.json
# then: run <case>/oracle.py against the clone → {pass|fail|error, reason}
```

`_state.py`'s cwd-relative `.planning/auto-pilot/state.json` means each clone is
isolated; `--force` is safe because nothing else shares that `.planning`.

**Inner branch-namespace fix (round-2, Codex P1-B):** the agent's `WorktreeManager`
names branches `auto-pilot/<contract_id>` (`_worktree.py:112`); identical spec ×
K repeats → identical contract IDs → branch collision if any object store is
shared. Separate clones avoid cross-case collision; within one clone, prefix the
run namespace with the eval run-id (`evals/<run_id>/...`) so a repeated case in
the same clone cannot clash. Each clone is torn down after its oracle runs
(explicit teardown — the outer clone is NOT auto-reaped by `WorktreeManager`).

### Components

```
evals/
  cases/<id>/
    spec.md      # task fed to orchestrator init --spec
    oracle.py    # def check(workdir: Path, run: RunResult) -> OracleResult
    meta.json    # {tags, difficulty, added_from, expected_phases}
                 #   (strictness is DERIVED from baseline 0-flips, not authored)
  results/<run_id>.json     # per-case outcomes for one eval run (cut1)
  baseline.json             # blessed per-case pass-rates + aggregate (cut1)
  history.jsonl             # append-only run summaries           (cut2)
  quarantine.txt            # unstable case ids, excluded from gate
scripts/evals/
  run.py          # corpus runner: select → clone → init→loop → oracle → aggregate
  oracle_api.py   # general check()/OracleResult contract + stdlib stat helpers
  regress.py      # compare run vs baseline → regression verdict (exit!=0 on fail)
  fingerprint.py  # harness content-hash + model/CLI id            (cut2)
  promote.py      # promote a real run → evals/cases/<id>           (cut2)
commands/
  eval-run.md      # /auto-pilot eval [--tier smoke|full] [--case ID] [--repeats K]
  eval-promote.md  # /auto-pilot eval promote <run_id>              (cut2)
```

`oracle_api.py` is a **general** contract — `check(workdir, run) -> OracleResult`
(`pass|fail|error` + reason). It does **not** wrap `_dogfood_gate.py`; those
plumbing helpers belong to Gate 2 only, offered as an optional import for
PM-loop-shaped cases, never as the task-success API.

### Regression signal (concrete statistics — no new dependency)

LLM runs are stochastic, so a single per-case pass→fail flip is expected noise,
not a regression. Therefore:

- **Repeats:** `--repeats K`, default **K=5** per case.
- **Baseline:** **N≥20** runs per case captured at bless time.
- **Unit of test:** the **aggregate** — Σpass over Σ(N·K) attempts, not per-case
  flips.
- **Statistic:** hand-rolled in stdlib `math` (repo has no scipy/numpy and
  deliberately avoids heavy deps — cf. `docs/perf-budget.md`). Use a **Wilson
  score interval** on the aggregate rate + a two-proportion comparison vs baseline.
- **Regression rule (concrete):** FAIL if the new run's aggregate-rate **upper
  Wilson bound (95%)** < baseline aggregate rate − **margin (default 0.05 absolute)**.
  Additionally FAIL on **error-count** rising above baseline error-count + tolerance.
- **Arming:** the gate is advisory (non-blocking) until Σ(N·K) ≥ **50** attempts;
  below that, report only.
- **Strict set vs quarantine:** a case enters the strict (gated) set only if it
  passed **K/K on every baseline run** (0 observed flips); any case with observed
  variance goes to `quarantine.txt`, excluded from the gate but still reported.

### error handling

- `error` (oracle crash / agent output unparseable) counts as **non-pass**
  (`success = pass / total_attempted`), and a spike in `error` count fails the
  gate. Only true infra faults (network, model 5xx) are retried, never silently
  dropped. Round-2: this closes the "regression hides as error" hole.
- Each `oracle.py` runs in its own subprocess with its **own timeout** (separate
  from the build timeout) — it executes agent-produced code and may hang.
- Case build timeout reuses the existing per-iter `--timeout-build`.

### Fingerprint (cut2) — content-hash, not environment snapshot

`fingerprint = sha(git HEAD) + hash(prompts/*.md) + hash(skills/auto-pilot/**) +
plugin version + model id + claude-CLI version`. **No "enabled skills"** (not
deterministically capturable — no `settings.json`, no skills-enable list in
`plugin.json`). `regress.py` only compares runs whose **model+CLI** match;
otherwise model drift is misattributed as harness regression.

### Cadence & cost (two-speed)

- **Per-PR gate (cheap, every change):** static only — `pytest`/`ruff`/`mypy` on
  `scripts/evals/` + a **meta-test** (a known-good case must pass, a deliberately
  broken case must fail) validating the oracle plumbing. Cents, seconds, **no
  agent runs.**
- **Full eval (expensive, scheduled):** the K×N agent runs. Nightly / pre-release
  / manual — **not** per-commit. One case ≈ $1–5 and minutes (`dogfood_tier1.sh`
  caps `--max-cost-usd 5.0`; `_config.py:17` defaults $50/4h). K=5 × N cases =
  tens of runs ⇒ budget with per-case and total ceilings, **fail-fast on exceed**,
  cases parallelized across clones. Cost ceiling granularity is **one iteration**
  (checked at iteration start, accrued at end — `headless-loop.py:204,224`); also
  pass `--max-cost-usd` to inner agent. Cost is best-effort (log-scrape with
  estimate fallback — `_budget.py:48`); accept the fuzz or move to
  `--output-format json` later.

---

## Reconciliation with existing `evals.json`

`skills/setup-harness/evals/evals.json` is the **legacy** LLM-judge format
(prompt → expected_output → judged expectations) — exactly the non-deterministic
style the locked decision rejects. The new `evals/cases/<id>/` deterministic tree
**coexists with and supersedes** it for harness-accuracy measurement. Porting the
setup-harness cases is **deferred** (not in cut1/cut2).

---

## Sequencing (anti-over-build)

- **Cut 1 (prove the signal):** `run.py` + `oracle_api.py` + **one real case**
  (the dogfood smoke spec with a *task-success* oracle on its `Verify cmd`, NOT
  `_dogfood_gate`) + `regress.py` vs a hand-written `baseline.json`. Gate 2 =
  keep existing `dogfood_tier1` as-is. Meta-test wired into the per-PR static gate.
- **Cut 2 (scale + attribute):** `fingerprint.py`, `promote.py`, `history.jsonl`,
  more cases, the `/auto-pilot eval promote` command. Only after cut1 shows the
  rate signal is non-noisy.

`regress.py` works in cut1 without `fingerprint.py` (compares a measured rate vs a
checked-in baseline number, like `docs/perf-budget.md`). **Cut1 precondition:**
baseline and re-run must be the **same model + CLI**; cut1 regress is advisory
across env changes until fingerprint lands in cut2.

## Out of scope (YAGNI)

No LLM-judge · no web dashboard (history.jsonl + printed summary) · no auto-promote
· no cross-project corpus (auto-pilot's own evals first) · no fingerprint/promote
in cut1.

## Testing

- **Meta-test** (per-PR gate): known-good case passes, deliberately-broken case
  fails → validates oracle plumbing without agent runs.
- **Unit:** `run.py` case selection + aggregation; `regress.py` Wilson/threshold
  math (table-driven, deterministic); `oracle_api` contract.
- **Dogfood absorption:** the existing dogfood smoke spec becomes the first eval
  case (task-success oracle), eating our own infrastructure.

## Open risks (carry into implementation)

1. Cost ceiling is per-iteration granular (≤1 iteration overshoot). Acceptable;
   documented.
2. `meta.json.expected_phases` must match `_count_phases` regex
   (`^#{1,3}\s+Phase` — `orchestrator.py:243`, floors at 1); assert at promote so
   a loose seed-spec heading style can't silently yield phase-count 1.
3. Full-eval wall-clock can be hours at larger N; mitigated by clone-parallelism +
   scheduled-only cadence.

## Review provenance

Two adversarial rounds (Codex `codex-adversarial` + cold `claude-reviewer`), each
verifying claims against repo file:line.

- **Round 1 → REJECT/REVISE.** 3 P0 (false `headless-loop --spec`; `_dogfood_gate`
  measures plumbing not task-success; "zero-flip" ignores stochasticity) + P1
  (fictional `swarm-bench`; cost; fingerprint; error-bucket; isolation). All folded
  into v2.
- **Round 2 → REJECT/REVISE.** All 3 P0 confirmed resolved. New P1: harness-health
  ungated (→ Gate 2); variance under-specified (→ concrete Wilson/K/N/margin);
  inner branch collision (→ separate clones + run-id namespace); `_dispatch.py`
  not a fan-out seam (→ N subprocesses). All folded into this v3.

Convergence trend: P0×3 → P0×0,P1 → (this) spec-detail. Remaining items are
implementation-grade, captured above as explicit sections/risks.

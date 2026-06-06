# Design — auto-pilot Evals Harness (SP4)

> Status: DESIGN **APPROVED** (v5, adversarially reviewed × 4 rounds — round 4 = dual
> APPROVE, 0 new P0/P1). Date: 2026-06-05.
> Source: brainstorming session. This is sub-project **SP4** of the larger
> "reliability harness" program (see [Program context](#program-context)).
> Next step after approval: `writing-plans` → implementation.

> **Cut 1 landed:** `scripts/evals/` + `evals/cases/dogfood-smoke/` + per-PR unit
> gate. Advisory only. See `evals/README.md`. Cut 2 (fingerprint/promote/history/
> blocking gate) not yet started.

## Purpose

Measure auto-pilot's **suite-level task success rate** over a corpus of tasks with
**deterministic** success oracles, track it over time, and **detect regressions** —
the "the suite silently dropped from 97% → 77% after a skill/prompt change" class
— attributing drops to harness changes.

The agent-under-test is **auto-pilot itself**: a harness change (prompt edit, hook
tweak, dispatch-protocol change, skill add/remove) that makes the PM-loop complete
spec phases less often must be caught by a number, not by vibes. This is the
measuring stick for the program's "fix the harness, not the output" principle.

**Scope of the claim (honesty note, round-3):** the *blocking* signal is the
**aggregate** success rate over the gated (stable) subset of cases — a corpus-wide
drop. It does **not** reliably flag a *single* case sliding 97%→77% in isolation;
per-case stochastic cases are quarantined out of the gate (see
[Regression signal](#regression-signal-concrete-statistics--no-new-dependency)) and
tracked advisory-only. The detector's minimum detectable effect (MDE) shrinks as
total attempts grow; at the arming floor it can only see large suite-level drops.

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
(the loop is state-driven). ~~`swarm-bench bench.sh` **does not exist** in this repo~~
`swarm/scripts/bench.sh` exists (round-1 finding was stale — bench.sh was added after
that audit). `_dispatch.py` is **ticket plumbing, not a fan-out
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
  never reads auto-pilot internals). This is the **suite-level** 97→77 detector
  (per-case-in-isolation drops are advisory-only — see Purpose honesty note).
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

`oracle_api.py` is a **general** contract — `check(workdir, run) -> OracleResult`.
It does **not** wrap `_dogfood_gate.py`; those plumbing helpers belong to Gate 2
only, offered as an optional import for PM-loop-shaped cases, never as the
task-success API. The two types the contract hands a case author (the one
interface every `oracle.py` touches — must be concrete, round-3 P1-C):

```python
@dataclass(frozen=True)
class RunResult:        # what the runner produces per case attempt
    returncode: int    # headless-loop exit code (0 ok, 2 = no state, 124 = timeout)
    status: str        # final state.json status, full enum (headless-loop.py:200):
                       #   success | stopped | pivot-needed | failed | cost-cap
                       #   (non-`success` ⇒ non-pass; oracle reads the deliverable, not status)
    state_path: Path   # the run's .planning/auto-pilot/state.json
    cost_usd: float    # best-effort (_budget.parse_session_usage, may be estimate)
    iters: int         # iterations consumed
    log_dir: Path      # claude session logs for this attempt
    workdir: Path      # the case clone root

@dataclass(frozen=True)
class OracleResult:
    outcome: str       # "pass" | "fail" | "error"
    reason: str        # human-readable; required for fail/error
```

### Regression signal (concrete statistics — no new dependency)

LLM runs are stochastic, so a single per-case pass→fail flip is expected noise,
not a regression. The gate therefore operates on the **aggregate over the stable
subset**, with these distinct symbols (round-3 P1-B — `N` was overloaded):

- **`K`** = repeats per case per eval run (`--repeats K`, default **5**).
- **`B`** = baseline runs per case captured at bless time (default **≥20**).
- **`C`** = count of **gated** cases (the strict subset, below).
- **gate attempts `A` = C · K** (this run); **baseline attempts = C · B · K**.

Rules:

- **Strict subset vs quarantine:** a case is **gated** only if it passed **K/K on
  every one of its B baseline runs** (0 observed flips). Any case with observed
  baseline variance → `quarantine.txt`: **excluded from the blocking gate**, run +
  reported **advisory-only** (an optional per-case rate-drop alert, never exit≠0).
  Consequence: the gated baseline rate is ≈1.0 by construction.
- **Statistic (stdlib `math`, no scipy/numpy — cf. `docs/perf-budget.md`):** compare
  the new gated-aggregate rate `p_new = Σpass/A` (for the gate, `total_attempted = A`)
  against the baseline gated-aggregate `p_base` using a **two-proportion score
  (Newcombe/Wilson) interval on the difference** `p_new − p_base` — this accounts for
  *both* runs' sampling error (round-3: a one-sample Wilson vs a fixed constant
  discards the baseline's CI).
- **Regression rule (concrete):** FAIL iff `upper95(p_new − p_base) < −margin`
  (margin default **0.05** absolute). Additionally FAIL if **error-count** rises
  above `baseline error-count + tolerance` (**tolerance default 0** — gated baseline
  error-count is ≈0 on the strict subset).
- **Arming:** blocking only when `A ≥ 50`; below that the rate gate is **advisory**
  (report, never exit≠0).
- **Known limit (MDE):** because the gated baseline ≈1.0, at `A=50` the rule only
  catches roughly a **≥10-point** suite drop (e.g. 45/50 = 90% does not fire; ≤44/50
  does). Smaller drops need larger `A`. State the MDE-vs-`A` curve in the dashboard
  so a "green" gate is never mistaken for "no regression below 10 points." This is
  the deliberate cost of deterministic, low-`K` evals — accepted, not hidden.

### error handling

- `error` (oracle crash / agent output unparseable) counts as **non-pass**
  (`success = pass / total_attempted`), and a spike in `error` count fails the
  gate. Only true infra faults (network, model 5xx) are retried, never silently
  dropped. Round-2: this closes the "regression hides as error" hole.
- Each `oracle.py` runs in its own subprocess with its **own timeout** (separate
  from the build timeout) — it executes agent-produced code and may hang.
- Case build timeout reuses the existing per-iter `--timeout-build`.
- **Clone teardown is `finally`/context-manager scoped, not "after the oracle"**
  (round-3 P2-D): the failure paths (loop crash, timeout-124, cost-cap, infra fault
  *before* the oracle runs) are the common ones during a real regression, so teardown
  must fire on every exit path or clones (with their inner git worktrees) leak.

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
- **Full eval (expensive, scheduled):** the `K·S` agent runs, where **`S` = all
  selected cases incl. quarantined** (quarantined cases still run for the advisory
  track) — `S ≥ C`, so cost is driven by `S`, not the gated subset `C`. Nightly /
  pre-release / manual — **not** per-commit. One case ≈ $1–5 and minutes
  (`dogfood_tier1.sh` caps `--max-cost-usd 5.0`; `_config.py:17` defaults $50/4h).
  `K·S` = tens of runs ⇒ budget with per-case and total ceilings, **fail-fast on
  exceed**,
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

- **Cut 1 (prove the *plumbing*, not the rate):** `run.py` + `oracle_api.py` + **one
  real case** (the dogfood smoke spec with a *task-success* oracle on its `Verify
  cmd`, NOT `_dogfood_gate`) + `regress.py` vs a hand-written `baseline.json`. Gate 2
  = keep existing `dogfood_tier1` as-is. Meta-test wired into the per-PR static gate.
  **By construction cut1's rate gate is always advisory** (1 case × K=5 = 5 attempts
  `< 50` arming floor, and a hand-written baseline cannot populate a strict subset) —
  `regress.py` in cut1 **never exits ≠0**. Cut1 proves clone→init→loop→oracle wiring
  and the meta-test, nothing statistical.
- **Cut 2 (arm the blocking rate gate):** measured baseline (B≥20 over enough cases
  to clear `A≥50`), `fingerprint.py`, `promote.py`, `history.jsonl`, the
  `/auto-pilot eval promote` command. The rate gate becomes blocking only here.

`regress.py` works in cut1 without `fingerprint.py` (compares a measured rate vs a
checked-in baseline number, like `docs/perf-budget.md`). **Cut1 precondition:**
baseline and re-run must be the **same model + CLI** (cut1 has no fingerprint to
detect env drift).

## Out of scope (YAGNI)

No LLM-judge · no web dashboard (history.jsonl + printed summary) · no auto-promote
· no cross-project corpus (auto-pilot's own evals first) · no fingerprint/promote
in cut1.

## Testing

- **Meta-test** (per-PR gate): runs the oracle against **checked-in fixtures**, not
  live agent runs (round-3 P2-F) — a `evals/_fixtures/{good,broken}/` pair (a
  recorded `workdir` + a synthetic `RunResult`); the oracle must pass `good` and fail
  `broken`. No clone, no agent, cents/seconds.
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
3. Full-eval wall-clock can be hours at larger corpora; mitigated by clone-
   parallelism + scheduled-only cadence.
4. **Peak clones unbounded** (round-3 P2): up to `C·K` concurrent `git clone --local`
   if all launch together; per-clone teardown bounds *steady-state* not *peak* disk.
   Cap with `max_parallel_clones` + `max_disk_gb` (fail-fast), clone from a read-only
   bare mirror, and assert no `git gc`/source mutation during a run (`--local`
   hardlinks are safe for *new* objects but fragile against concurrent gc).

## Review provenance

Three adversarial rounds (Codex `codex-adversarial` + cold `claude-reviewer`), each
verifying claims against repo file:line.

- **Round 1 → REJECT/REVISE.** 3 P0 (false `headless-loop --spec`; `_dogfood_gate`
  measures plumbing not task-success; "zero-flip" ignores stochasticity) + P1
  (fictional `swarm-bench`; cost; fingerprint; error-bucket; isolation). Folded → v2.
- **Round 2 → REJECT/REVISE.** All 3 P0 confirmed resolved. New P1: harness-health
  ungated (→ Gate 2); variance under-specified (→ concrete stats); inner branch
  collision (→ separate clones + run-id namespace); `_dispatch.py` not a fan-out
  seam (→ N subprocesses). Folded → v3.
- **Round 3 → REJECT/REVISE.** All prior fixes confirmed encoded; **every repo claim
  re-verified accurate**; architecture declared sound by both. New P1 (all in the
  statistics narrative): strict-set excludes the per-case 97→77 example (→ honesty
  note + suite-level reframe); `Σ(N·K)`/`N` overloaded + cut1 can't arm (→ `C/K/B`
  symbols + cut1-advisory-by-construction); `RunResult` undefined (→ schema);
  two-proportion named but only one-sample Wilson built (→ difference-interval test).
  P2: peak-clone disk cap, `finally` teardown, meta-test fixtures. **Folded → this v4.**

- **Round 4 (final gate) → dual APPROVE.** Both reviewers independently re-derived
  the difference-interval statistics in stdlib (confirmed direction, the 44/50-fires
  / 45/50-passes MDE boundary, and improvement-immunity) and re-verified every
  sampled repo claim. **0 new P0/P1.** Only P2 doc-precision nits — all folded → v5
  (RunResult.status full enum; error `tolerance` default 0; cost symbol `S = C +
  quarantined`; `total_attempted = A` for the gate; "suite-level" 97→77 label).

Convergence trend: **P0×3 → structural-P1 → statistics-prose-P1 → definitional-P2 →
APPROVE**. The architecture stabilized at round 2; rounds 3–4 closed self-consistency
+ definitional gaps. Design approved for `writing-plans`.

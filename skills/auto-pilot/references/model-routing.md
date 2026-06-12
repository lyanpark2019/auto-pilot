<!-- Shared contract: multi-agent model routing (PM / workers / verifiers).
     This file is the wire-in SoT for model selection across the PM loop;
     global ~/.claude/CLAUDE.md and per-project runbooks cite it instead of
     restating the matrix. Lives under skills/auto-pilot/references/ (NOT
     agents/ — recursive agent auto-discovery would surface it as a ghost
     agent, the review-core.md defect). -->

# Model Routing — PM, workers, verifiers, and the rebalance ledger

## Machine form (code reads the yaml, humans read this file)

`skills/auto-pilot/references/model-routing.yaml` is the machine SoT consumed by:

- `scripts/_routing.py:1` — narrow resolver (`effort_for_tier`, `lower_effort`, `codex_timeouts`, `verifier_min_tier`, `model_rank`)
- `scripts/codex_review_bounded.py:1` — bounded codex invocation (tiered effort → timeout → one lower-effort retry → ABSTAIN review.json)
- `hooks/verifier-tier-gate.sh:1` — PreToolUse(Task) deny of under-tier verifier `model:` overrides

Facts live once: tier semantics here, config values in the yaml.

## Tier ladder

T0 `Fable` > T1 `Opus 4.8` > T2 `Opus 4.6` > T3 `Sonnet 4.6 (1M ctx)` > T4 `Haiku 4.5`.
Codex side ladder: `gpt-5.5 xhigh` > `high` > `medium` (default) > `low` / mini models.
Agent-tool `model:` override accepts only `sonnet|opus|haiku|fable` — an exact pin
(e.g. Opus 4.6) requires the `model:` field in an agent definition's frontmatter.

## Role × model matrix

| Role | Default | When | Fallback chain |
|---|---|---|---|
| PM / advisor | Fable | plan, coordinate, gate, final judgment — never edits code | → Opus 4.8 (max thinking effort) |
| Worker-Heavy | opus (4.8) | architecture, cross-cutting refactor, migration, risk=high | → Opus 4.6 → sonnet + upgraded verification |
| Worker-Primary | sonnet (1M) | multi-file implementation; mandatory when ctx > 150k | ctx overflow → split the task, never swap model |
| Worker-Mechanical | haiku | rename, codemod, boilerplate, doc formatting | → codex low / mini |
| Worker-Narrow (codex) | gpt-5.5 medium | ≤2-file well-typed port; xhigh for narrow-but-hard ports | 429 / quota / 10-min hang → same-tier Claude worker |
| Verifier | ≥ PM tier | cold context, read-only, reports to PM directly | see Verifier convention |

## Codex dispatch

- Effort: `medium` default; `xhigh` for narrow hard ports; `low`/mini for mechanical work.
  Wire: `codex exec -c model_reasoning_effort="<effort>"` (+ `-m <model>` when pinned).
- Runner choice: one-shot job expected ≤10 min → `codex exec` subprocess;
  long-running / needs observation / interactive → tmux pane.
- Codex is a second opinion, never a consensus blocker (abstain → accept Claude verdict).
- Enforced: the auto-pilot codex reviewer derives the diff's risk tier
  (`scripts/risk_assess.py`) and dispatches through
  `scripts/codex_review_bounded.py` — effort per
  `skills/auto-pilot/references/model-routing.yaml` `codex.effort_by_risk_tier`,
  bounded by `codex.timeout_s`/`codex.retry_timeout_s`, honest ABSTAIN on
  exhaustion (accepted by `scripts/_evidence.py` only with `abstain_reason`).

## Verifier convention

Verification dispatches use a model **at or above the PM's tier**, cold context,
read-only, verdict returned straight to the PM.

- Single (cold Claude reviewer): routine PR rounds.
- Dual (codex + cold Claude, adversarial): risk-high merge gates, phase-end
  milestones, or the user's explicit deep-review keyword.
- Reuse existing agents — `feature-dev:code-reviewer`, `codex:codex-rescue`,
  `auto-pilot:swarm-verifier`, `auto-pilot:review-gatekeeper`, `goal-judge`.
  Do not author new verifier agents; this doc only assigns model tiers.
- Enforced: `hooks/verifier-tier-gate.sh` denies a verifier Task dispatch whose
  explicit `model:` override is below `verifier_min_tier`
  (`skills/auto-pilot/references/model-routing.yaml`). Frontmatter models are
  audit scope, not hook scope.

## Routing ledger & PM rebalance

Per-project dispatch history lives at `<repo>/.claude/routing/ledger.yaml`
(committed; schema: `schemas/routing-ledger.schema.json` in this plugin).
The PM appends one record per finished task at phase end and rebalances from
evidence:

- **Promote** — same (role, task_class) fails `gates_first_try` twice in a row,
  or a real P0 escapes the worker: move that assignment up one tier.
- **Trial demotion** — three consecutive records with `review_rounds == 1`,
  first-try gate pass, and `rejects_real == 0`: run the NEXT task one tier
  lower as a trial. Verification stays at the original tier during the trial;
  any real finding reverts the assignment immediately.
- Demotion is evidence-based right-sizing only. Cost-motivated downgrades stay
  forbidden (global hard rule); cost is a tiebreaker between models the ledger
  shows as equivalent — never the reason to drop a tier.
- Every change is appended to `rebalance_log` with the triggering rule and the
  evidence task ids, so the next PM session can audit or revert it.

Rotation: keep the latest 50 records (or 90 days); archive older records to
`.claude/routing/archive/ledger-<YYYYQn>.yaml`.

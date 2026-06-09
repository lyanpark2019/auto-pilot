# Hermes-Loop MVP — design spec

> Status: design approved 2026-06-09, pre-implementation. Scope frozen via
> brainstorming + dual adversarial review (Codex gpt-5.3 + cold Claude Opus, both
> REJECTed the v1 draft; this is the review-driven v2). Implementation plan is a
> separate document (writing-plans output).

## 1. Problem

The `retro` agent (`agents/retro.md`) already mines per-run artifacts and appends
prose `trap → consequence → guard` lessons to `.claude/insights.md` (append-only,
grep-dedup, evidence-cited). What no component does today:

- accumulate a **cross-run** occurrence count for a recurring pattern,
- hold a machine-readable lifecycle for an improvement candidate,
- emit a **deterministic** gate verdict that says "this pattern has recurred enough
  to be worth promoting into a skill/hook/schema".

Promoting a recurring friction into a durable harness asset is therefore a manual
human read of prose. This MVP adds the missing structured layer **without**
auto-modifying any asset: it discovers candidates, counts them across runs, and
reports a gate verdict. Acting on the verdict stays human.

## 2. Scope (frozen decisions)

| Decision | Value | Source |
|----------|-------|--------|
| Components | improvement-ticket schema + `learning_miner.py` + ledger | brainstorm Q1 |
| Miner write surface | **discover-only** — writes `state=candidate` only | brainstorm Q3 |
| Identity | per-pattern **fingerprint** | brainstorm Q2 |
| Ledger durability | durable, **outside the target repo** | review v2 (reverses Q2 "committed") |
| Analyzer shape | deterministic Python, no LLM; mirrors `risk_assess.py` | brainstorm |
| `retro` agent | **untouched** | brainstorm + review #5 |

### Non-goals (explicit YAGNI)

asset-usage sidecar/hook, context-cache, FSM transitions beyond `candidate`,
auto-drafting promotion assets, git-trailer / docs-plan mining, parsing
`insights.md` prose, any edit to `retro`.

## 3. Why v1 was rejected (review provenance)

Both reviewers REJECTed the first draft. Every load-bearing claim was verified
against the repo before accepting the finding.

| # | Sev | Finding | Evidence |
|---|-----|---------|----------|
| 1 | P0 | `finding_hash` unfit as fingerprint seed: line# in payload → unstable across runs; first-8-token truncation → distinct findings collide (proven empirically). | `scripts/_subagent_helpers.py:46-48` <!-- cite-ignore --> |
| 2 | P0 | Committed ledger derived from gitignored inputs → evidence `path:line` dangles on fresh clone; SoT inversion. | `.gitignore:2,5` <!-- cite-ignore --> |
| 3 | P0 | Target-repo pollution — the loop runs on arbitrary user repos; default-committing a tracked dir dirties their VCS and leaks finding text. | brownfield-driver purpose |
| 4 | P1 | No flock/atomic on read-modify-write bump; repo mandates lock+atomic for state writes. | `scripts/_state.py:122-130` <!-- cite-ignore --> |
| 5 | P1 | Parsing `insights.md` prose is brittle AND contradicts "retro untouched". | `agents/retro.md:46-58` <!-- cite-ignore --> |
| 6 | P1 | `pivot_detector` keyed `phase-N`, per-run scratch → wrong granularity for cross-run counting. | `scripts/orchestrator.py:200` <!-- cite-ignore --> |
| 7 | P1 | Schema lacks run/plugin lineage → stale candidates contaminate counts; raw-occurrence threshold gameable within one run. | `scripts/orchestrator.py:88` <!-- cite-ignore --> (`run_id` exists) |
| 8 | P1 | Schema must be validated before any persist. | — |

## 4. Architecture (v2)

```
schemas/improvement-ticket.schema.json   NEW  ticket record (JSON Schema 2020-12)
scripts/_improvement.py                  NEW  fingerprint + ticket I/O + lock + validate
scripts/learning_miner.py                NEW  CLI: scan inputs, bump ledger, emit verdict
tests/test_improvement.py                NEW  TDD: fingerprint + ticket I/O + lock + schema
tests/test_learning_miner.py             NEW  TDD: CLI + verdict matrix + dry-run + parallel-bump
~/.claude/projects/<slug>/improvements/  NEW  durable ledger home (per project, untracked)
```

`retro`: unchanged. `risk_assess.py`: the shape precedent — module-level policy dict,
advisory exit 0, `--fail-on` exit 2, single-line JSON verdict.

### 4.1 Ledger location

Default: `~/.claude/projects/<project-slug>/improvements/<fp>.json`, the same
per-project home as session auto-memory (`<MEMORY_DIR>` in
`skills/doc-management/references/rebuild-phases.md:16`). Properties:

- **durable** — survives `git clean` in the target repo (it lives outside it),
- **no pollution** — never writes into the target repo's tracked tree or VCS,
- **per-project** — slug derived from repo root, like the memory dir.

Opt-in override: `--commit-to <path>` writes the ledger to a tracked path **only**
when the operator explicitly asks (auto-pilot's own dogfood, where PR-reviewable
tickets are wanted). Never the default.

### 4.2 Fingerprint

`fp = sha256(source ‖ 0x1f ‖ file_basename ‖ 0x1f ‖ normalized_issue ‖ 0x1f ‖ candidate_asset_or_empty)`

`normalized_issue` = lowercase, collapse whitespace, strip absolute/relative paths,
line numbers, ISO dates, and any `phase-N` prefix. **Full** issue text is kept (no
8-token truncation — that was finding #1's collision source). The miner builds this
itself; it does **not** seed from `finding_hash`.

### 4.3 Inputs (MVP = 2 structured sources)

- `.planning/auto-pilot/critic-rejections-phase-*.jsonl` — reviewer findings.
- `.planning/auto-pilot/state.json` — `pivot_detector` doom-loop entries.

Both are per-run scratch under `.planning/`. The miner reads them per run and
accumulates into the durable home ledger; the `phase-N` scoping and line numbers in
these sources are normalized away during fingerprinting (#6). `insights.md` is **not**
an input (#5).

### 4.4 Evidence is self-contained

Each ticket's `evidence[]` entry stores a **copied issue snippet** plus the `run_id`
it came from — never a dangling `path:line` into a gitignored scratch file (#2). A
ticket therefore remains meaningful after the source run's `.planning/` is wiped.

### 4.5 Writes (concurrency-safe)

Every ledger mutation is a read-modify-write under flock + atomic temp+rename,
reusing the repo's existing atomic-write helper (`scripts/_contract.py`) plus a
per-ledger lock (`scripts/_state.py` flock pattern). A parallel-bump test asserts two
concurrent miners on the same `<fp>.json` converge to the correct count (#4).
Schema validation runs before any persist; an invalid record is refused, not
written (#8).

## 5. improvement-ticket.schema.json

```
schema_version   const 1
fingerprint      string ^[a-f0-9]{64}$        == filename stem
state            enum candidate|accepted|implemented|verified|promoted|rejected
pattern          string                       normalized one-line description
source           enum reviewer-finding|doom-loop|pivot|insight|wasted-tool
candidate_asset  enum skill|hook|schema|test|doc|cache | null
occurrences      integer ≥1                   raw bump count (telemetry)
distinct_runs    integer ≥1                   count of unique run_ids (gate uses THIS)
first_seen       date-time
last_seen        date-time
plugin_version   string                       auto-pilot version that observed it
repo_fingerprint string                       stable id of the target repo
evidence         array<{ run_id:string, snippet:string, source_path?:string,
                         locator?:string }>  minItems 1
promotion_gate   { tests_pass:bool|null, ci_pass:bool|null, user_approved:bool|null }
notes            string (optional)
additionalProperties: false
```

MVP writes only `state=candidate`. The full FSM is declared so the on-disk format is
stable for future, human-driven transitions; nothing enforces transitions yet (noted,
not hidden).

## 6. learning_miner.py — CLI

Mirrors `risk_assess.py`:

- default → scan inputs, bump the home ledger, print a human report + one-line JSON verdict.
- `--dry-run` → compute **projected in-memory** counts and verdict, write nothing. The
  projection includes the would-be bump so a dry verdict matches a real persist.
- `--fail-on promotable` → exit 2 when verdict is `promotable` (hook/CI wiring); else exit 0.
- `--repo-root PATH` (default cwd), `--commit-to PATH` (opt-in tracked ledger), `--json`.
- `now` is injected (no bare `datetime.now()` in the hot path), per repo discipline.

Verdict JSON: `{"verdict":"promotable|thin","candidates":N,"promotable_count":M,"by_asset":{...}}`

## 7. Gate (count threshold, honestly described)

Promotion threshold table = single SoT (module-level dict, like
`risk_assess.REVIEW_POLICY`). Threshold is on **`distinct_runs`**, not raw
`occurrences` (a noisy worker re-tripping a finding twice in one run must not
auto-promote — #7):

- `reviewer-finding` with `distinct_runs ≥ 2` → `promotable`
- `doom-loop`/`pivot`/`wasted-tool`/`insight` with `distinct_runs ≥ 3` → `promotable`
- else → `thin`

Contract: `thin` = STOP (no promotion fan-out worth dispatching). `promotable` =
unlock the future human-driven promotion step. This is a **count gate**, not a
diagnosis — it is deliberately *not* claimed as 1:1 with the rebuild-phases Phase-0
audit (which is human judgment). It borrows only the STOP/proceed hard-gate shape.

## 8. Testing (TDD, RED first)

`tests/test_learning_miner.py` + `tests/test_improvement.py`:

- schema: validates a well-formed ticket; rejects extra prop / bad state / short fingerprint / empty evidence.
- fingerprint **stability**: same logical finding at a shifted line / different path / different date → **same** fp.
- fingerprint **collision-resistance**: two semantically different findings → **different** fp (the v1 truncation regression).
- bump: second scan of the same pattern in a **new run** → `occurrences=2`, `distinct_runs=2`, `last_seen` updated, evidence appended (no dup snippet).
- one-run re-trip: same pattern twice in the **same** run → `occurrences=2`, `distinct_runs=1` → still `thin`.
- verdict matrix: reviewer `distinct_runs` 1→thin / 2→promotable; doom-loop 2→thin / 3→promotable.
- `--dry-run` leaves the ledger byte-identical; its verdict equals the next real persist's verdict.
- `--fail-on promotable` → exit 2 when promotable, 0 when thin.
- empty / missing inputs → `thin`, no crash, exit 0.
- parallel-bump: two concurrent processes bumping the same `<fp>.json` → final count correct (flock).

Gates: mypy + ruff clean; ≤500 lines per file (split is planned, not discovered —
both new scripts registered in `scripts/quality/module_size_budget.txt` if needed);
schema reachable by the existing schema-validation test pattern.

## 9. Residual risk (보수적·냉정)

- **Repo fingerprint stability** — `repo_fingerprint` derivation (remote URL vs root
  path) must be stable across clones of the *same* project or distinct_runs counting
  fragments. Decide the derivation in the plan; test it.
- **Slug collision** — two repos with the same basename share a
  `~/.claude/projects/<slug>/` home. Mitigated by `repo_fingerprint` inside tickets,
  but the directory is shared; document it.
- **Two structured inputs only** — dropping `insights.md` means human-authored
  retro lessons never become tickets in the MVP. Accepted; a structured
  `insights.jsonl` from retro is a separate future spec that *does* touch `retro`.
- **No promotion automation** — `promotable` only reports. If no human acts, tickets
  accumulate `distinct_runs` indefinitely with no decay. Decay/TTL is out of MVP scope;
  flagged for the next iteration.

# Ticket schema — Phase 4/5 work units

Each finding from Phase 2 becomes one or more tickets. A ticket is **the smallest unit a single subagent can complete and the PM can verify**.

## Schema

```yaml
id: T-NN
title: short imperative, ≤60 chars
priority: P0 | P1 | P2
scope_files:           # touch ONLY these
  - path/to/file.py
  - path/to/other.py
out_of_scope_files:    # explicitly forbidden, prevents creep
  - path/to/related-but-touch-not.py
why: |
  1-2 lines linking to user criterion or audit finding.
acceptance:
  - acceptance criterion 1 (objective, testable)
  - acceptance criterion 2
  - test_command_exits_0: pytest src/tests/foo -x
  - grep_proves: 'rg "removed_symbol" src/ | wc -l = 0'
depends_on: [T-XX]     # optional, run after these
parallel_safe: true|false
estimated_loc_delta: -120 / +50 / etc.  # rough; helps catch scope creep
```

## Examples

### P0 ticket — surface cleanup

```yaml
id: T-01
title: rename _cag_generation → cag_generation, prune __init__ re-exports
priority: P0
scope_files:
  - src/application/generators/sports_content/_cag_generation/__init__.py
  - src/application/generators/sports_content/_cag_generation/  # (rename to cag_generation)
  - src/application/generators/sports_content/generator.py
  - src/models/structured_output/__init__.py
out_of_scope_files:
  - src/application/generators/sports_content/_cag_generation/_mixin.py  # logic inside untouched
why: |
  W10 found _-prefixed module imported externally in 154 files; __init__ re-exports
  130+ symbols, half private. Surface API score 42; biggest single drag on composite.
acceptance:
  - grep 'from .*_cag_generation' src returns 0 (after rename done across all callsites)
  - models/structured_output/__init__.py exports <60 symbols, no _-prefixed
  - pytest src/tests -x exits 0
  - mypy --strict src exits 0
depends_on: []
parallel_safe: false  # touches __init__ used by many tracks
estimated_loc_delta: -200 (re-exports removed; rename is mechanical)
```

### P0 ticket — schema-prompt alignment

```yaml
id: T-04
title: add Pass enum value to HandicapRecommendation/TotalRecommendation
priority: P0
scope_files:
  - src/models/structured_output/_picks.py
  - src/prompts/base_common.md     # if reciprocal prompt change needed
out_of_scope_files:
  - src/models/structured_output/_validators_*.py  # validator unchanged
why: |
  W7 found base_common.md:85-86 allows "Pass" output but enum lacks it; LLM that
  follows prompt gets validation error. P0 because it can silently break prod.
acceptance:
  - enum values include PASS for both Handicap and Total
  - test added that constructs Pass instance for each
  - existing tests pass
parallel_safe: true
estimated_loc_delta: +20
```

### P1 ticket — mixin merge

```yaml
id: T-06
title: merge _cag_generation 6-file mixin chain into single deep module
priority: P1
scope_files:
  - src/application/generators/sports_content/_cag_generation/_mixin.py
  - src/application/generators/sports_content/_cag_generation/_blocks_mixin.py
  - src/application/generators/sports_content/_cag_generation/_calls_mixin.py
  - src/application/generators/sports_content/_cag_generation/_helpers.py
  - src/application/generators/sports_content/_cag_generation/__init__.py
out_of_scope_files:
  - src/application/generators/sports_content/_cag_generation/_persist.py  # already independent
why: |
  W3 + W4 both flagged: 955 lines split into 6 files purely to pass <500 rule.
  Single 800-line deep module is more navigable. Module-size lint allows up to 800
  for orchestrators per project rule.
acceptance:
  - 6 mixin files merged into 1 (cag_generator.py, ≤800 lines)
  - all public methods preserved (grep proves)
  - pytest src/tests/application/generators/sports_content -x exits 0
parallel_safe: true (no shared files with other tracks once T-01 done)
estimated_loc_delta: -150 (header/import removal)
depends_on: [T-01]
```

### P1 ticket — validator band-aid

```yaml
id: T-08
title: remove _sync_bilingual_numerics band-aid; fix at schema level
priority: P1
scope_files:
  - src/application/generators/sports_content/_cag_generation/_helpers.py
  - src/application/generators/sports_content/_cag_generation/_calls_mixin.py
  - src/models/structured_output/_picks.py  # if structural fix needed
out_of_scope_files:
  - src/models/structured_output/_validators_arithmetic.py  # separate ticket
why: |
  W4 flagged _sync_bilingual_numerics copies KO confidence→EN pick before strict
  validation — masks LLM bugs. Per feedback_no_post_hoc_numeric_validator,
  fix should be at schema level (single bilingual confidence field) not post-hoc copy.
acceptance:
  - _sync_bilingual_numerics function removed
  - schema enforces single source of truth for confidence/reason/risk
  - smoke test (N≥2) passes — see .claude/rules/quality-bar.md
parallel_safe: false  # schema change ripples
estimated_loc_delta: -60
depends_on: [T-01, T-04]
```

### P2 ticket — perf

```yaml
id: T-11
title: persist proto_cag fire-and-forget off critical path
priority: P2
scope_files:
  - src/application/generators/sports_content/_cag_generation/_mixin.py  # or renamed
out_of_scope_files:
  - src/infrastructure/database/  # persistence impl untouched
why: |
  W6 found _persist_proto_cag awaited serially before LLM call; ~5-15% wall-clock saving.
acceptance:
  - LLM call and persistence run via asyncio.gather (or task spawn)
  - error in persistence doesn't crash generation (logged)
  - existing tests pass
parallel_safe: true
estimated_loc_delta: +10
depends_on: [T-06]
```

## Dispatch logic

PM groups tickets by:

1. **parallel_safe AND no overlapping scope_files** → dispatch in same Agent batch.
2. **depends_on** → wait for prerequisite to complete + verify before starting.
3. **out_of_scope_files** declared upfront prevents two parallel tracks colliding.

When in doubt about overlap, sequence. Re-dispatching a clean retry is cheaper than a 3-way merge conflict.

## Per-ticket execution prompt (sent to subagent)

```
You are executing T-NN: <title>

ABSOLUTE CONSTRAINTS:
- Touch ONLY files in scope_files. Modifying out_of_scope_files = ticket fails.
- Do NOT add new features. Implement the smallest change satisfying acceptance.
- Do NOT introduce new abstractions, helpers, or modules unless acceptance requires it.

SCOPE FILES:
<list>

OUT OF SCOPE (forbidden):
<list>

WHY:
<why>

ACCEPTANCE (you must satisfy all):
<list>

WORKFLOW:
1. Read each scope_file fully.
2. Make minimum change.
3. Run: <project test command, e.g., pytest -x src/tests>
4. Run: <linter, e.g., ruff check src && ruff format --check src>
5. Commit with conventional commit format. Do NOT push.
6. Report: files changed, LOC delta, test output (last 20 lines), acceptance verification per item.

If a constraint or acceptance criterion cannot be met, STOP and report. Do not retry.
```

## PM verification per ticket

When subagent reports done, PM:

1. `git diff --stat <branch>` — sanity check LOC delta vs estimate.
2. Re-run acceptance test commands; do not trust agent's "tests pass" claim.
3. `git log --oneline -1 <branch>` — confirm commit message format.
4. For removal tickets, run the `grep_proves` line manually.

Only after PM verification → mark ticket done in TaskList. Otherwise: re-dispatch with sharpened constraint.

## When to split a ticket

Split if any of:
- Estimated LOC delta > ±300 (too big to review).
- scope_files >5 unrelated files.
- Acceptance has >5 criteria.
- depends_on graph creates a 3+ deep chain.

Split into per-file or per-concern subtickets (T-06a, T-06b, etc.).

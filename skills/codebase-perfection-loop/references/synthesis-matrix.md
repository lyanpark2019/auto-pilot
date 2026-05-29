# Synthesis matrix — PM verdict format

After Phase 1 workers complete, the PM (Claude Opus 4.7) assembles a single-page verdict. This is the only thing the user reads from the audit; do not dump raw worker output.

## Output template

```markdown
## Composite: NN / 100  (target: 95+)

| Dim | Score | Weight | Critical findings |
|---|---|---|---|
| Layer boundaries | 95 | 1.0 | PASS |
| Module size & deep-modules | 88 | 1.0 | <file>.py 1100L = artificial 3-mixin split |
| Surface API | 42 | 1.5 | `_cag_generation` private-but-imported externally; CLI 4 dead flags |
| Type safety | 70 | 1.0 | `Any` 1669×; type:ignore 102; hot-path leaks |
| Test architecture | 88 | 1.0 | 4 files >1000L; 0 monkeypatch path violations |
| Perf / infra fit | 85 | 1.0 | 2 RTT reducible; persist on critical path |
| AI navigability | 65 | 1.5 | 7 module CLAUDE.md redirect to external vault |
| Dead code & dup | 92 | 1.0 | 1 deletable; 5 suspect; 3 dup hotspots |
| Config / secrets | 75 | 1.0 | 57 direct getenv calls; 15 missing in .env.example |
| Docs coherence | 60 | 1.0 | 418 .md files; 285 auto-generated; vault external |

**Worst 3 (priority sort)**:
1. Surface API 42 — see [W10 details](#)
2. Docs coherence 60 — see [W2 details](#)
3. AI navigability 65 — see [W3 details](#)

## P0 (blockers, must fix for 95+)

- T-01 — fix surface: rename `_cag_generation` → `cag_generation`, prune `__init__` re-exports
- T-02 — remove dead CLI flags (`--mode`, `--tool`, `--compact`, `--bullet-context`)
- T-03 — repo self-containment: rewrite 7 module CLAUDE.md as 30-line self-contained
- T-04 — schema-prompt alignment: add Pass enum to HandicapRecommendation/TotalRecommendation
- T-05 — wiki-tree harness: build `.claude/{rules,architecture,runbooks,branding,prompts}/`

## P1 (within-cycle fixes)

- T-06 — merge `_cag_generation` 6-file mixin → 2-3 deep modules
- T-07 — remove `PlayerToolStrategy` (= `Tool` Protocol duplicate)
- T-08 — replace validator band-aid `_sync_bilingual_numerics` with structured-output fix
- T-09 — clean `env_bool` bypass (1 site); add 15 missing `.env.example`
- T-10 — consolidate `home`/`away` string literals (14 sites) into constants

## P2 (deferred unless time)

- T-11 — perf: `_persist_proto_cag` fire-and-forget
- T-12 — perf: `_resolve_league_id` Stage 1 fold
- T-13 — perf: natstat home+away single SQL
- T-14 — test coverage P0: `_data_fetcher`, `context_builder` unit tests
- T-15 — naming: unify `_tool_player_{bs,bk,vl,sc}` vs folder forms

## Approved (post Phase 3 decisions)

- Vault policy: **archive → `.claude/`** (single SoT)
- PR strategy: **Phase A code → Phase B docs, multiple PRs each**
- Existing docs: **delete all** (clean slate)

## Phase 4 dispatch plan

Parallel tracks (each = 1 Agent in one message):
- Track A1 (T-01, T-02): surface cleanup — `src/interface/cli/`, `src/models/structured_output/__init__.py`
- Track A2 (T-04): prompt-schema alignment — `src/models/structured_output/_picks.py`, `src/prompts/`
- Track A3 (T-06, T-07): mixin merge — `src/application/generators/sports_content/_cag_generation/`
- Track A4 (T-08): validator band-aid — `src/application/generators/sports_content/_cag_generation/_helpers.py`
- Track A5 (T-09, T-10): config cleanup + literal constants

Sequential after A1-A5 pass: Phase B docs rewrite (see Phase 5 plan).
```

## How to write the synthesis

1. **Read every worker output** completely. Don't skim.
2. **Cross-reference** — if W4 (adversarial) and W3 (architecture) both flag the same issue, the finding is corroborated (high confidence). If they diverge, note both.
3. **Score each dim** using `big-tech-rubric.md`. Be honest. Don't inflate.
4. **Group findings into tickets** following `ticket-schema.md`. One ticket touches one concern.
5. **Assign P0/P1/P2** by impact-on-composite. P0 = unblocks crossing 95 threshold.
6. **Identify parallel-safe sets**. Tickets touching disjoint files → parallel. Overlapping → sequence.
7. **Quote actual file:line citations**. No "various places" — exact pointers.

## Weighting formula

```
composite = (
    layer_boundaries * 1.0
  + module_size      * 1.0
  + surface_api      * 1.5
  + type_safety      * 1.0
  + test_arch        * 1.0
  + perf_infra       * 1.0
  + ai_navigability  * 1.5
  + dead_code_dup    * 1.0
  + config_secrets   * 1.0
  + docs_coherence   * 1.0
) / 11.0
```

Surface and AI-nav are weighted 1.5 because they have outsize impact on whether future agents/engineers can actually work with the code.

## Stop conditions per loop iteration

- Composite ≥ 95 AND every cell ≥ 85 → done.
- 2 consecutive loops without ≥3-point composite gain → diminishing returns; ship and defer.
- User says "ship it" → ship.
- Phase 4 introduces regression detected by Phase 6 re-score → revert offending ticket(s), re-plan.

## What NOT to include in synthesis

- Raw worker JSONL.
- Phrases like "we should consider" — say what changes, not what to consider.
- "Various" / "many" / "multiple" — always quote N and a representative.
- Speculation about root causes — that goes in the ticket if needed.
- Praise. No "great work" or "well structured overall" — the user already knows the wins; they hired the audit for the gaps.

The synthesis is a diff between current state and 95+. Keep it that.

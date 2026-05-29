# Big-tech 95+ rubric

Score each dimension 0–100. **95+ requires every dimension ≥85**.

The rubric is **context-adjusted**: solo-dev / small-team scoring rewards simplicity and penalizes over-engineering, where a FAANG infra team would expect the opposite. Set the project's context (in `.claude/branding/context.md`) before scoring.

## 10 dimensions

### 1. Layer boundaries (weight 1.0)

| Score | Meaning |
|---|---|
| 95+ | Zero wrong-direction imports. Domain knows nothing about infra. Test verifies. |
| 85 | ≤2 violations, each justified by docstring. |
| 70 | ~5 violations; some unjustified. |
| <50 | Layers are decorative; everything imports everything. |

**Check**: `grep -r 'from src.infrastructure' src/domain` (and equivalents per layer/language).

### 2. Module size & deep-module doctrine (weight 1.0)

| Score | Meaning |
|---|---|
| 95+ | >threshold files are justified (composition root, data dictionary, sport-specific table). No artificial splits. |
| 85 | ≤2 files over threshold; one suspect split. |
| 70 | Multiple artificial 3-file mixin splits visible. |
| <50 | Everything is wrapper. |

**Check**: `find src -name '*.py' -exec wc -l {} + | sort -rn | head -20`. Each >threshold needs a 1-line justification in module CLAUDE.md.

### 3. Surface API (weight 1.5)

| Score | Meaning |
|---|---|
| 95+ | Public vs private is unambiguous. Underscored names not used from outside. `__init__.py` re-exports only intended API. CLI flags all read. |
| 85 | <5 minor boundary violations. |
| 70 | "Private" boundary regularly crossed. CLI has 1-2 dead flags. |
| <50 | `_module` imported from external code AND `__init__.py` re-exports 100+ private symbols. |

**Check**: see W10 in worker-scopes.

### 4. Type safety / static checks (weight 1.0)

| Score | Meaning |
|---|---|
| 95+ | `mypy --strict` (or `tsc --strict` / equivalent) passes. `Any` <50 occurrences, justified. `# type: ignore` <10. |
| 85 | Strict mode passes; `Any` count moderate. |
| 70 | Loose mode passes; `Any` everywhere on hot path. |
| <50 | Type checker disabled or errors suppressed wholesale. |

**Check**: `mypy --strict src` exit 0, then `rg -c 'type: ignore' src`, `rg -c ': Any' src`.

### 5. Test architecture (weight 1.0)

| Score | Meaning |
|---|---|
| 95+ | Clear unit/integration/e2e split. Mocks at boundaries only. Tests run in <2 min. No permanent skip. |
| 85 | 1-2 large test files; classification mostly clear. |
| 70 | Some false-integration (mock-heavy named "integration"); slow run. |
| <50 | Tests pass but never call production code paths. |

### 6. Performance / infra fit (weight 1.0)

| Score | Meaning |
|---|---|
| 95+ | Async correct. Concurrency primitives in right places. DB queries N+1-free. Infra matches scale. |
| 85 | 1-2 serializable awaits on hot path. |
| 70 | Multiple low-hanging perf wins; some N+1. |
| <50 | Misuses async (event loop blocking) OR infra wildly over-scaled (K8s for 100 req/day). |

### 7. AI navigability / repo self-containment (weight 1.5)

| Score | Meaning |
|---|---|
| 95+ | Cold AI can enter repo, read CLAUDE.md → architecture → entry point in 4 hops and grok the flow. Module CLAUDE.md self-contained. |
| 85 | Entry clear; module docs sparse but present. |
| 70 | Some module docs redirect to external vault that repo doesn't include. |
| <50 | Module CLAUDE.md are 1-line stubs; entire knowledge in external system. |

### 8. Dead code & duplication (weight 1.0)

| Score | Meaning |
|---|---|
| 95+ | Zero verified dead code. Duplication <3 hotspots, each with documented reason. |
| 85 | <5 candidates, all in "suspect / report only" tier. |
| 70 | Several dead modules retained "just in case". |
| <50 | Substantial dead code; multiple parallel implementations of the same logic. |

**Check**: `vulture src --min-confidence 80` (Python) or equivalent.

### 9. Configuration / secrets (weight 1.0)

| Score | Meaning |
|---|---|
| 95+ | One settings module. `getenv` called only there. Secrets only in env / secret manager; never repo. `.env.example` complete. |
| 85 | 1-2 stray `getenv` calls (bootstrap order); justified. |
| 70 | Env vars read in 10+ places. |
| <50 | Secrets in `.env` committed; `getenv` everywhere. |

### 10. Documentation coherence (weight 1.0)

| Score | Meaning |
|---|---|
| 95+ | Wiki-tree harness applied. Every claim verifiable. No stale TODO >6mo. README matches code. |
| 85 | 1-2 stale entries; structure correct. |
| 70 | Old plan docs scattered; auto-generated module ref committed. |
| <50 | 100+ .md files of mixed staleness, no clear SoT. |

---

## Weighted composite

```
composite = (Σ score_i × weight_i) / Σ weight_i
```

With weights `surface=1.5`, `ai_nav=1.5`, others `=1.0`, the divisor is 11.0.

**95+ project**: composite ≥ 95 AND every cell ≥ 85.

**85–94**: solid; ship-worthy; usually has 1-2 cells below 85.

**70–84**: works but has structural debt that will compound.

**<70**: refactor before next feature.

## Triggering a re-score

After Phase 4/5 lands, re-run **W1 (size), W3 (arch), W4 (adversarial), W10 (surface)** only — these are the fastest signal on whether structural debt actually went down. The slower ones (W2 docs, W5 tests, W9 drift) revisit on the next full loop.

## Context-adjustment examples

| Project type | Adjusted floor for "infra overkill" cell |
|---|---|
| Solo dev / single EC2 | Penalize K8s, multi-region, feature-flag-system as 0–30 |
| 3-person startup | Penalize as 50–60 |
| 50-person product team | Standard rubric |
| FAANG infra | "Infra simplicity" cell becomes "infra rigor"; flip the scoring |

State the context in `.claude/branding/context.md` so future audits know the floor.

---
name: diagnosing-llm-output-leaks
description: Use when an LLM generation pipeline (CAG, RAG, structured output) produces unwanted tokens in target language output and prompt-level fixes are not converging. Triage map for "is this a data-layer leak, a prompt leak, or LLM stochasticity?". Use before iterating prompt directives a 3rd time on the same leak.
---

# Map

## Step 0 — what kind of leak is it?
Run pattern scanner on N≥10 fresh samples across the largest sport/persona/profile axis. Aggregate by `(pattern, # of matches affected)`. Then classify:

| Affected matches | Class | Fix surface |
|---|---|---|
| ≥ 80% (e.g. 8+/10) | **Data-layer leak** | atomic tool / composer / fact builder. Prompt directives will NOT fix. |
| 30–79% | **Prompt leak** | base prompt rule, anti-pattern table, terminology map |
| 1–2 matches only | **Stochasticity** | N=1 noise, do not "fix". Re-test N≥2 next iteration. |
| All matches, single token | **Single source** | one builder function emits the offending token. Grep + fix. |
| Random tokens, random matches | **Model drift** | model/temperature change, not prompt |

## Step 1 — verbatim or hallucinated?
For each top-N leaked token, check whether the token appears in the **structured input** (Composer facts, prompt context, atomic tool output).

| Result | Class | Fix |
|---|---|---|
| Token in input | **Verbatim leak** | LLM is citing a "locked fact". Fix at the *emitting* function, not the prompt. |
| Token not in input | **Hallucination** | LLM invented it. Fix via prompt anti-pattern + retry validation. |
| Token in input as English, used in non-English prose | **Bilingual gap** | The fact builder needs `_en/_ko` variants (Path A migration). |

## Step 2 — top-token frequency rule
- The top 1–3 banned tokens usually account for 30–60% of all violations.
- Fixing the top 1 token at the data layer often eliminates more leaks than 3 prompt iterations.
- "Total violations" is misleading; **unique tokens** is the real complexity metric.

## Step 3 — when to stop iterating on prompt
| Symptom | Action |
|---|---|
| 2 consecutive prompt edits, same leak still ≥ 80% affected | Stop. Switch to data-layer audit. |
| Leak count drops 50%+ between iterations | Continue prompt iteration. |
| Leak count oscillates within ±20% | Stochasticity, not signal. N≥2 each iter. |
| New leak appears that wasn't in baseline | Regression. Revert and isolate. |

## Step 4 — universal vs partial in concrete terms
- **Universal** (≥ 80%): one upstream function emits it. ONE grep + ONE fix kills hundreds of violations.
- **Partial** (30–79%): prompt rule reaches some calls but not others. Strengthen rule with concrete BAD/GOOD example from observed evidence.
- **Stochastic** (≤ 20%): below LLM noise floor at typical temperature. Do not chase.

## Step 5 — locked-fact verbatim trap
LLMs treat structured input fields labelled `[LOCKED FACTS]`, `[VERBATIM]`, `[CITE EXACTLY]` as untouchable strings. If the locked fact is in the wrong language for the target section, the LLM cites it verbatim and the leak is structural.

**Fix pattern (Path A bilingual split)**:
- Builder function returns `(en, ko)` tuple instead of single string.
- Composer prompt block presents both with explicit `_EN`/`_KO` labels.
- Prompt directive: cite the matching language variant by VALUE, not by LABEL.
- Verify with N≥2 smoke before declaring fix.

## Step 6 — when to ignore a leak
| Leak | Action |
|---|---|
| Cosmetic (label inside parentheses, e.g. `(5G)`) | Ignore unless reader-facing |
| Inside JSON-only field (`reason_codes`, `risk_codes`) | Ignore — enum, not prose |
| In stats_comparison structured `away_value`/`home_value` | Ignore — these are tabular, not prose |
| In trace metadata / debug fields | Ignore — never reaches user |

## Diagnostic recipe (paste-ready)
```bash
# 1. Pull N fresh samples
# 2. Run scanner on each
# 3. Aggregate by_pattern → count + matches_affected
# 4. List top 15 specific banned tokens with frequency
# 5. For each top token: grep the codebase for the exact string
# 6. If found in atomic tool / composer / builder → data-layer fix
# 7. If found only in prompt examples → prompt fix
# 8. If not found anywhere → hallucination (rare)
```

## Anti-patterns
- "Add another anti-pattern row to the prompt table" after 2 iterations failed → **wrong direction**, escalate to data layer.
- "Re-run smoke until it passes" → cherry-picking. Use N≥2 consecutive at same temperature.
- Counting `total_violations` instead of `(unique_token, # matches affected)` → masks the leverage point.
- Fixing the lowest-count tokens first → start with the dominant token (Pareto).
- Accepting "the LLM is just bad at this" before checking the data layer → almost always wrong.

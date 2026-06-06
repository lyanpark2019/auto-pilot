---
name: diagnosing
description: >-
  Two diagnostic modes for runtime/output mismatches.
  MODE llm-output-leaks — use when an LLM generation pipeline (CAG, RAG,
  structured output) produces unwanted tokens in target language output and
  prompt-level fixes are not converging. Triage map for "is this a data-layer
  leak, a prompt leak, or LLM stochasticity?". Use before iterating prompt
  directives a 3rd time on the same leak.
  MODE stale-runtime — use before claiming a file/class/function is dead or
  alive, when source code and runtime behavior disagree, when "removed" code
  still appears in output, when restart doesn't fix it, when prompt/template/
  config change isn't taking effect, when cache seems stale, when investigating
  two-process races, or when comparing handoff/memory claims to current code
  state. Map of universal checks for runtime-vs-source mismatch.
---

# Diagnosing

Pick the mode that matches the symptom:

- **`llm-output-leaks`** — LLM output contains unwanted tokens; deciding whether
  to fix at the data layer, the prompt, or not at all.
- **`stale-runtime`** — runtime behavior disagrees with source; deciding whether
  code is dead/alive, why a change isn't taking effect, or whether a handoff
  claim is still true.

---

# MODE: llm-output-leaks

> absorbed diagnosing-llm-output-leaks + diagnosing-stale-runtime 2026-06-07

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

---

# MODE: stale-runtime

> absorbed diagnosing-llm-output-leaks + diagnosing-stale-runtime 2026-06-07

## Alive or dead?
| Question | Check |
|---|---|
| Still called? | `grep -rn 'name(' src --include='*.py'` exclude tests. 0 caller = dead. |
| Class still used? | Class in MRO ≠ method invoked. Check call sites, not definition. |
| Really deleted? | Stub with same signature is not deletion. Verify body, not name. |
| Memory/handoff says "removed"? | Verify on disk + verify caller count. Docs drift; code is authoritative. |

## Source disagrees with runtime — order
1. Find process (`ps -ef`, parent, start time, cwd, cmdline).
2. File mtime vs process start time. File-after-start = stale in memory.
3. Trace metadata: `extra.trace.raw_*` vs `extra.trace.post_*` shows which stage diverged.
4. `@lru_cache` / module-level singletons / registry decorators / `import` side effects freeze at first call.
5. `>1` writer to same target without lock = silent overwrite.
6. **Form hypothesis only after 1–5.**

## Symptom → first check
| Symptom | Check |
|---|---|
| DB row has old version label | `extra.schema_version` + `extra.prompt_version` BEFORE blaming code |
| "Restart didn't fix it" | Restart raced with file rewrite — mtime vs process start |
| Cache stale across iteration | `@lru_cache` without per-iter `cache_clear()` |
| Two writers race | `flock` per key, or DB unique index. Cross-host needs DB-level. |
| Removed function appears in trace | Stub vs delete. Inspect body, not name. |
| Output corrupted | Search trace for `raw_*` / `pre_*` vs `post_*` / `final_*` snapshot pairs. Diff = mutating stage. |
| Prompt rule not effective | Process imported pre-change version; cache_clear or full restart |
| Some matches clean, some broken in same minute | Two processes, no lock, both writing |

## N=1 LLM smoke is noise
- Single-run delta < ~40% at temperature ≥ 0.7 = drift, not signal.
- Require ≥2 consecutive runs before declaring success or regression on prompt/model change.

## Production change verification
- After deploy: query the FIRST data point produced by the running process. Compare its trace metadata against expected. Disk state ≠ runtime state.
- Restart alone proves nothing. Verify by *next emitted artifact*.

## Stub vs delete
| | Stub | Delete |
|---|---|---|
| Signature | kept | removed |
| Body | neutered (no-op / pass-through) | removed |
| Caller imports | still work | fail |
| Future reactivation risk | yes (one typo) | no |
| Audit rule | check body + caller count + MRO inheritance | check `git log -- path` |

## Trace fields worth searching when output looks wrong
- `raw_*_preview`, `pre_*`, `unprocessed_*`, `input_*` — pre-pipeline snapshot
- `post_*_preview`, `final_*`, `processed_*`, `output_*` — post-pipeline snapshot
- `*_version`, `schema_*`, `prompt_*`, `model_*` — what code/config was active
- Diff raw vs processed → identifies mutating stage

## Process-restart mechanics
- `@lru_cache(maxsize=N)` on file-reading functions: frozen at first call. Survives across requests within process. Cleared only by `cache_clear()` or process exit.
- Editable install (`pip install -e .`) `.pth` adds path to `sys.path`. Same dir as cwd usually. Verify with `cat .venv/lib/python*/site-packages/__editable__.*.pth`.
- PM2/supervisord auto-respawn: child PID changes, parent stays. `kill <child>` triggers respawn from current disk state.
- Race: `git pull && pm2 restart` ordering matters. If pm2 restart fires before git checkout finishes writing, new process imports old files.

## Two-process write race (silent overwrite)
- UPSERT without unique constraint + no app-level lock = both writes succeed, last wins.
- Per-key `fcntl.flock` on lockfile under `/tmp/<app>-locks/` covers same-host. Cross-host needs DB-level (advisory lock or unique constraint).
- OS releases `flock` on process exit — crash-safe.

## Handoff doc vs code
- Handoff/memory claim = "true at write time, possibly stale now".
- Before acting on "X was removed/added/changed":
  - Read the file.
  - Grep callers.
  - `git log -- <path>` for last touch.
- Code is authoritative for present-tense facts. Docs are authoritative for *why*.

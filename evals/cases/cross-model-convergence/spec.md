# cross-model-convergence — does codex + claude pick the SAME defect class?

The durable, re-runnable spec for R1's last open unknown. The R1 fix (PR #102/#105)
keys a reviewer-finding fingerprint on a controlled-vocab `class` so the same defect,
phrased differently, collapses to one promotable ticket. That collapse only happens
**cross-model** if the codex reviewer and the claude reviewer independently pick the
SAME class token for one defect. Same-model collapse is proven; cross-model is not.

## Fixture

`seed.diff` adds two files, **each with exactly ONE defect** that maps cleanly to ONE class:

| file | defect | expected class |
|---|---|---|
| `stats.py` | `percentile(values, 1.0)` → `k=int(len(s)*1.0)==len(s)` → `s[k]` IndexError (empty case is guarded, so this is the sole defect) | `index-out-of-bounds` |
| `parse.py` | `first_token("")` → `text.split()==[]` → `tokens[0]` IndexError on empty input | `unguarded-empty-input` |

`defects.json` is the machine-readable defect → class map the analyzer matches against,
**by file basename only**. The analyzer reuses the real miner's fingerprint, which carries
no line number, so it cannot split two defects in one file — `_validate_defects` REQUIRES
one defect per basename (put each seeded defect in its own file).

## Procedure

1. **Produce** (live, budgeted): `scripts/measure_cross_model_collect.py --diff <seed.diff>
   --out <runs> --passes 3` dispatches the REAL claude-reviewer and codex-reviewer over
   the frozen `seed.diff`, K passes each, writing `<runs>/<model>/pass-N/review.json`.
   Codex ABSTAIN (usage limit / double timeout) is recorded and tolerated.
2. **Analyze** (deterministic): `orchestrator.py measure-cross-model --runs <runs>
   --defects defects.json --json` runs the REAL miner over the collected reviews and
   reports, per defect: each model's class multiset + modal class, `cross_model_agree`,
   and `cross_model_promotable` (a single fingerprint whose evidence spans BOTH models
   and clears the reviewer-finding threshold).
3. **Persist** the analyzer JSON + `shasum -a 256` as evidence; record the number in
   `docs/architecture.md` (R1 block) and memory.

## Reading the result

- **converges** (modal classes match, `cross_model_promotable` true) → R1's cross-model
  assumption holds; the gate can fire from a codex+claude pair.
- **fragments** (modal classes differ) → the gap is quantified; a remedy (class-alias
  clustering / single-reviewer-source promotion / judge canonicalization) is a SEPARATE
  follow-up — not built here.

## Honest limits

K is small (codex usage-limited) → the first number is a SIGNAL, not a definitive rate.
Two defects only → convergence varies by class; report per-defect, do not generalize to
all 16 classes. The producer skips preflight/contract gates (faithful for class
*selection*, not a full e2e loop).

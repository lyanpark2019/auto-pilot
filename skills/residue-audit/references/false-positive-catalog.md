# False-positive catalog

Things deterministic tools (vulture / jscpd / ruff) and naive agents flag as
residue that are actually LIVE. Drop these from findings, or report them as
`FALSE-POSITIVE (keep)` with the reason. Re-litigating them every audit is waste;
documenting them once is the cure. (memory: `feedback_idx_scan_zero_not_unused`,
`feedback_agent_scan_signal_not_truth`)

Each entry: **what the tool sees** → **why it's actually live** → **how to confirm**.

---

## 1. pytest fixtures (name-injection)

- **Tool sees:** a function with 0 callers.
- **Reality:** pytest injects fixtures by matching the parameter NAME of a test
  function to the fixture function name. There is never an explicit call.
- **Confirm:** `@pytest.fixture` decorator, or it lives in `conftest.py`; grep test
  signatures for the fixture name as a parameter:
  `grep -rn "def test_.*\b<fixture_name>\b" app/tests/`.

## 2. `if False:` / unreachable-looking async-gen idioms

- **Tool sees:** dead branch / unreachable code.
- **Reality:** `if False:` blocks are sometimes deliberate type-only or
  doc/placeholder idioms; `yield` inside an `if False:` is a known trick to mark a
  function as an async generator without emitting. Removing it changes the
  function's type (coroutine vs async-gen).
- **Confirm:** read the function — is it used where an async generator is expected?
  Is the block guarded by a comment explaining intent? If so, keep.

## 3. OpenAPI `responses=` examples + Pydantic `json_schema_extra`

- **Tool sees:** large literal dicts with no code reading them → "dead data".
- **Reality:** these are LIVE schema. FastAPI's `responses={...}` example dicts and
  Pydantic `model_config = {"json_schema_extra": {...}}` are consumed by the schema
  generator at runtime to build the OpenAPI doc. No application code reads them by
  name, but deleting them silently degrades the public API contract.
- **Confirm:** the dict is an argument to a route decorator (`responses=`) or sits
  in a model's `model_config` / `json_schema_extra`. Keep.

## 4. `__init__.py` re-exports

- **Tool sees:** `from .foo import Bar` where `Bar` is never used in `__init__.py`.
- **Reality:** the import IS the public API — it re-exports `Bar` so callers can do
  `from package import Bar`. Often paired with `__all__`.
- **Confirm:** the unused import is in an `__init__.py`, and/or the symbol is in
  `__all__`. Keep. (Do NOT let ruff `F401` auto-strip `__init__.py` re-exports —
  configure `__init__.py` to allow F401 or use explicit `__all__`.)

## 5. DI-container-wired classes — incl. dormant / flag-gated subsystems

- **Tool sees:** a class instantiated only inside a DI/composition-root file, or not
  at all when the feature flag is off → "unused class".
- **Reality:** the class is wired into the container and resolved at runtime by type.
  A **dormant subsystem is not dead code** — a flag-gated or reserved API (e.g. a
  `revoke_strict` / `unrevoke` security pair, a canary-only path, a default-off
  circuit breaker) is fully wired and becomes reachable when the flag flips.
  Deleting it removes a deliberate, reviewed capability.
- **Confirm:** the class/type appears in a provider / composition root / DI registry;
  there is a feature flag or config gate referencing the feature. Keep, and note
  "dormant — flag-gated" in the FALSE-POSITIVE list.

## 6. Runtime predicate builders (`.eq_if()` / `.in_()` etc.) with 0 literal hits

- **Tool sees:** a method or column/field name with 0 grep hits as a literal → "unused".
- **Reality:** query builders, filter DSLs, and PostgREST-style predicate helpers
  compose conditions at runtime from variable names; the literal symbol never appears
  as a hard-coded string. An index/column with `idx_scan=0` is NOT proof it's unused —
  the query may build the predicate dynamically. (`feedback_idx_scan_zero_not_unused`)
- **Confirm:** grep for the builder method and dynamic construction
  (`.eq_if(`, `.in_(`, `.filter(`, f-string/`.format` building column names); read
  the call site. If the name can be produced at runtime, keep.

## 7. Entry points (cross-ref Gate 3)

- **Tool sees:** route handler / cron target / CLI command with 0 in-repo callers.
- **Reality:** invoked by the framework / scheduler / OS, not by in-repo code. Zero
  callers is BY DESIGN.
- **Confirm:** see `six-gate.md` Gate 3. Keep.

---

## When a "duplicate" is a BUG, not a refactor

jscpd flags two near-identical spans. Before merging them into one helper, prove
they are **behavior-identical**. If they diverged — one scrubs PII and the other
doesn't, one logs and the other is silent, one handles an error path the other
drops — that divergence is a **bug**, not a dedup opportunity:

- Do NOT silently merge to whichever copy you grabbed first.
- Surface the divergence, decide which behavior is correct, and ship that as a
  deliberate **bugfix PR** — separate from any dedup refactor (diff-hygiene).

A duplicate is only safe to dedupe when the copies are provably equivalent.

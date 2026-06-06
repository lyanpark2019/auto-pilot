# Dead-code 6-gate

Before ANY deletion of a symbol/function/class/module, ALL six gates must PASS.
**Any single uncertain gate → REPORT ONLY. Never blind-delete.** Tools (vulture,
ruff, an agent) produce *candidates*; this gate produces *decisions*. A candidate
is a hypothesis until it survives all six. (memory: prohibitions dead-code rule,
`feedback_no_delete_move`, `feedback_agent_scan_signal_not_truth`)

If the symbol is a **misplaced live file** (right code, wrong location), the action
is **move**, not delete (`feedback_no_delete_move`).

---

## Gate 1 — Static grep = 0

Direct text search finds zero live references. Tools miss string-form and
test-only references, so grep yourself — including tests AND SQL:

```bash
SYM=the_symbol
grep -rn "\b${SYM}\b" app/                       # all source, incl. tests
grep -rn "\b${SYM}\b" app/ --include='*.sql'     # RPC bodies, migrations reference by literal name
grep -rn "${SYM}" app/tests/                     # test-only usage still = live
git grep -n "${SYM}"                             # respects .gitignore, fast
```

Any hit you cannot positively rule out (e.g. it's only in a comment, or only the
definition itself) → re-read each hit. If a real call site exists → **FAIL** (not dead).

## Gate 2 — No dynamic import / getattr / string-dispatch

The symbol is not reached by a name computed at runtime:

```bash
grep -rn "getattr\|importlib\|__import__\|globals()\|locals()\|operator.attrgetter" app/
grep -rn "\"${SYM}\"\|'${SYM}'" app/             # symbol referenced as a STRING literal
```

Dispatch tables, plugin registries, `entry_points`, Celery/RQ task names, and
`getattr(module, name)` all reference symbols by string — invisible to AST tools.
If the symbol's *name* appears as a string anywhere live → **UNCERTAIN/FAIL**.

## Gate 3 — Not a route / cron / CLI entry point

It is not an externally-invoked entry point (called by a framework/scheduler/OS,
not by in-repo code):

- FastAPI/Flask/Django route handler (decorated, registered in a router)
- cron / pg_cron / scheduler target (referenced from a cron table or job config)
- CLI command (Click/Typer/argparse subcommand, `console_scripts`)
- webhook handler, signal receiver, lifecycle hook (`startup`/`shutdown`)

```bash
grep -rn "@router\.\|@app\.\|add_api_route\|include_router" app/   # is it a route?
grep -rn "console_scripts\|entry_points\|add_command\|@cli\." .    # CLI entry?
```

Entry points have zero in-repo callers BY DESIGN — grep=0 here is expected and
does NOT mean dead. → **FAIL** (keep) if it's an entry point.

## Gate 4 — Not framework-reflection-registered

It is not kept alive by framework reflection / registration:

- **FastAPI**: route function, dependency (`Depends(...)` target), exception handler.
- **Pydantic**: a model class, field, `@field_validator`/`@model_validator`,
  `@computed_field`, `Config`/`model_config`. Validators look unused — they're
  invoked by Pydantic, never called directly.
- **pytest**: a fixture (consumed by parameter-name injection, never an explicit call),
  `conftest.py` hooks, parametrize ids.
- **DI container**: a class wired into a composition root / provider — including a
  **dormant or flag-gated** subsystem. Reserved/disabled APIs (e.g. a
  `revoke_strict` / `unrevoke` security pair behind a feature flag) are NOT dead;
  they are wired and reachable when the flag flips. (`feedback_idx_scan_zero_not_unused`)
- ORM/SQLAlchemy declarative models, marshmallow schemas, serializers.

```bash
grep -rn "Depends(\|@field_validator\|@model_validator\|@computed_field\|@pytest.fixture" app/
grep -rn "${SYM}" <di-container-or-providers-file>    # wired into DI?
```

If reflection/registration keeps it alive → **FAIL** (keep).

## Gate 5 — Not in `__all__` / re-export

It is not part of a public surface re-exported elsewhere:

```bash
grep -rn "__all__" app/ | grep "${SYM}"
grep -rn "from .* import .*${SYM}\|import ${SYM}" app/   # re-exported via __init__.py?
```

A symbol listed in `__all__` or re-exported through an `__init__.py` is public API;
external/downstream callers may use it even with 0 internal call sites. → **FAIL** (keep)
unless you've confirmed no downstream consumer.

## Gate 6 — Full test suite green after removal

The canonical test suite passes with the symbol removed — using the project's
canonical invocation, not a bare serial subset:

```bash
# remove on a throwaway branch, then:
ruff check app/ && mypy app/ && pytest -n auto app/tests/
```

Show the output. A green run with the deletion applied is the final confirmation.
If you cannot run the full suite, this gate is **UNCERTAIN** → report-only.

---

## Decision

| Gates | Action |
|-------|--------|
| 6/6 PASS | Safe to delete (or move if misplaced-live). Ship as its own ≤300 LOC PR. |
| any UNCERTAIN | **REPORT ONLY.** Record which gate and why. Do not delete. |
| any FAIL | Not dead. Mark `FALSE-POSITIVE (keep)` with the gate that saved it. |

The FALSE-POSITIVE (keep) list is a deliverable: it documents why apparently-dead
code is alive, so the next audit doesn't re-litigate it.

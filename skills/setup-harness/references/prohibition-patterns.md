# Prohibition Patterns by Framework + AI-Specific Anti-Patterns

Format each entry as: prohibition | reason (incident/ADR/PR). Without a "why," agents ignore the rule.

---

## AI-generated code anti-patterns (cross-language)

Snyk/OX Security research: **36–40% of AI-generated code contains security vulnerabilities**. The "Comments Everywhere" pattern shows in 90–100% of AI-generated repos. Enforce these at the linter level — agents can't ignore CI failures.

| Anti-pattern | Detection | Reason |
|--------------|-----------|--------|
| `any` type abuse (TS) | `@typescript-eslint/no-explicit-any` at error level | Agents fall back to `any` when inference fails — use `unknown` + type guards |
| Ghost files (new file instead of edit) | ast-grep + filename convention rule | Agent creates `userServiceV2.ts` next to `userService.ts` rather than editing |
| Comment floods | comment-ratio check (>30% lines) | "Comments Everywhere" pattern; signal of low confidence |
| Code duplication | jscpd / Plankton duplicate detection | Agent skips codebase search, generates fresh implementation |
| Plain-text secrets | gitleaks / git-secrets pre-commit | 36–40% of AI code ships vulns |
| `eval` / `new Function` | eslint-plugin-security | Common AI shortcut for dynamic dispatch |
| Missing input validation | Zod/Pydantic schema required at boundaries | Bypassed when agent rushes happy path |
| Default exports | Factory.ai grep-ability rule | Hurts agent grep efficiency on later sessions |

---

## OpenAI's four lint-rule categories (from harness-engineering blog)

Frame every custom linter rule under one of these:

1. **Grep-ability** — named exports, consistent error types, explicit DTOs. Increases agent hit rate when walking codebase with grep.
2. **Glob-ability** — predictable file structure. Lets agent reliably place/find/refactor files.
3. **Architecture boundaries** — block cross-layer imports. Enforce dependency direction with domain allowlists.
4. **Security/privacy** — block plain secrets, mandate input schema validation, forbid `eval`.

Error messages should follow this structure (educates the agent as it runs):

```
ERROR: [what is wrong] [file:line]
WHY:   [why this rule exists, link to ADR]
FIX:   [concrete fix steps]
EXAMPLE:
  // Bad:  import { db } from '../infra/database';
  // Good: import { DatabaseProvider } from '../domain/providers';
```

The agent can ignore CLAUDE.md docs but **cannot ignore CI failures**. Put rule documentation inside the error message.

---

## Python / FastAPI

| Prohibition | Reason |
|-------------|--------|
| Service calling Supabase/DB directly | Layer boundary violation — use Repository (ADR-XXX) |
| `match_date`/`match_time` columns | Use `match_datetime` (UTC) + `match_datetime_kr` (KST) — past timezone bug |
| `response.data[0]` without cast | mypy: use `cast(dict[str, Any], ...)` |
| f-string in logger | Use lazy `%s`: `logger.info("msg %s", val)` — eager formatting cost |
| `BackgroundTask` without `observable_task()` wrapper | Silent data loss — fire-and-forget needs metrics |
| `extra="allow"` on response DTOs | Arbitrary fields leak to API — use `extra="ignore"` |
| `HTTPException.detail` non-string | Must be `str` per FastAPI spec |
| `Depends(...)` returning ORM object | Couples handler to DB — return DTO |
| Sync I/O inside `async def` | Blocks event loop — use `asyncio.to_thread` or async lib |

---

## Node / TypeScript / Next.js

| Prohibition | Reason |
|-------------|--------|
| `console.log` in production code | Use structured logger (pino/winston) — log searchability |
| `any` type assertions | Use `unknown` + narrowing — TS-1 anti-pattern |
| Direct DB queries in API routes | Use service/repository layer — testability |
| `process.env` scattered in code | Centralize in `config.ts` — runtime validation |
| Default exports | Hurts grep-ability + tree-shaking — use named exports |
| Inline Zod schema | Co-locate DTOs in `src/dtos/[domain]/[action].dto.ts` |
| `useEffect` for derived state | Use `useMemo` — React anti-pattern |
| Server component importing client component without `'use client'` boundary | Next.js bundle bloat |

---

## Go

| Prohibition | Reason |
|-------------|--------|
| `interface{}` / `any` parameters | Use generics (1.18+) — type safety |
| Ignored errors (`_, _ = ...`) | errcheck — silent failure |
| Goroutines without context cancellation | govet — leak risk |
| `fmt.Println` in production | Use structured logger (slog) |
| Unbounded slice growth | Pre-allocate with `make([]T, 0, capacity)` |

---

## Rust

| Prohibition | Reason |
|-------------|--------|
| `.unwrap()` / `.expect()` in lib code | clippy `unwrap_used = "deny"` — explicit error handling |
| `#[allow(clippy::...)]` to silence lint | `allow_attributes = "deny"` — fix code, not config |
| `dbg!` macro in committed code | clippy `dbg_macro = "deny"` |
| `mod.rs` files | Use `name.rs` next to `name/` dir — Rust 2018+ idiom |

---

## Universal (any language)

| Prohibition | Reason |
|-------------|--------|
| Hardcoded magic numbers/URLs | Use named constants or config — searchability |
| Source files >300 lines | SRP violation — split by responsibility |
| `git add -A` / `git add .` | Risk committing secrets/build artifacts — explicit names |
| `git commit --no-verify` | Bypasses pre-commit linter; ban in hook |
| `--dangerously-skip-permissions` | Disables safety hooks |
| Manual SSH deploy | Use CI/CD only — reproducibility |
| `.env` editing by agent | Secrets exposure |
| Destructive git without confirmation | `branch -D`, `reset --hard`, `push --force` — irreversible |
| Linter config edit to silence error | Fix code, not rule — `protect-lint-config.sh` hook |
| Force-push to main/master/prod | Rewrites shared history |

---

## Database / Supabase

| Prohibition | Reason |
|-------------|--------|
| DDL on transaction pooler | Read-only — use session pooler |
| Schema change without `NOTIFY pgrst` | PostgREST cache stale → 4xx errors |
| RPC overload (same name, different params) | PGRST203 ambiguity error |
| RPC with `SET search_path = ''` | Tables not found — must be `'public'` |
| Team name columns in DB | Use `team_id + sport` key, resolve names in API layer |
| `*` in `SELECT` for hot paths | Bandwidth + index coverage — list columns explicitly |

---

## Infra / DevOps

| Prohibition | Reason |
|-------------|--------|
| `terraform apply` against prod from agent | PreToolUse-block; require human |
| `kubectl apply` against prod from agent | Same — blast radius |
| Public S3 buckets / open security groups | Conftest+OPA policy gate |
| Missing `container-structure-test` | CI guard before image push |
| Docker `latest` tag in prod manifest | Non-reproducible deploy |

---

## LLM app

| Prohibition | Reason |
|-------------|--------|
| Required field marked in prompt only | Use structured output schema instead |
| PostProcessor band-aid for output bug | Fix Context/prompt/schema upstream |
| Single smoke test for LLM call | N≥2 — LLM is probabilistic |
| Arithmetic in prompt | Locked facts only, no inference math |
| Mock LLM in integration tests | Real call — mocks hide schema drift |

---

## How to mine prohibitions for your repo

1. `git log --oneline --grep="fix\|revert\|hotfix\|incident"` → top 30
2. For each → identify the pattern that caused it
3. Encode the pattern as a lint rule (custom ESLint/ast-grep/ruff rule)
4. Add the rule to ADR
5. Add **one CLAUDE.md line** pointing to the ADR
6. Delete from CLAUDE.md anything the linter now catches

Iterate every time the agent makes a new mistake. One rule = every future session protected.

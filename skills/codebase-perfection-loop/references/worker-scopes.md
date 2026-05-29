# Worker scopes — 10 parallel audit workers

Each worker is a self-contained prompt sent to a `Agent` background invocation. The PM (Claude Opus 4.7) dispatches all 10 in one message, blocks until ≥8 complete, then synthesizes.

## Model assignment

| Role | Model | Why |
|---|---|---|
| PM / synthesis / code review / verification | **Claude Opus 4.7** (`claude-opus-4-7`) | Best at multi-source synthesis, long context, careful verification |
| Adversarial workers (W4, W7) | **Codex 5.5 high** (`gpt-5.5-high` via `codex:codex-rescue`) | Independent second opinion; finds blind spots Claude misses by design |
| Structural workers (W1, W2, W5, W8) | `Explore` subagent (Claude Sonnet 4.6 underlying) | Fast, read-only, grep/find heavy |
| Plan workers (W3, W6, W10) | `Plan` subagent | Architecture reasoning |
| Git/memory drift (W9) | `general-purpose` subagent | Cross-cuts everything; needs Bash + Read access |

## Universal prompt prefix

Every worker prompt starts with:

```
PROJECT: <repo path>
LANGUAGE: <auto-detected>
OTHER WORKERS COVER: <comma-separated list of W# topics>
YOUR SCOPE: <this worker's topic ONLY — do not duplicate other workers>
OUTPUT: markdown, <max-words> words, format below.
FORBIDDEN: <topics other workers own>
```

This "you cover X, others cover Y, don't duplicate" framing is critical. Without it, workers redundantly grep the same data 10 times — wasted tokens, conflicting verdicts.

---

## W1 — Code size / dead code / duplication (Explore)

```
Scope (only):
1. Files exceeding language size threshold (Python 500, TS 400, Go 600, Rust 500).
   Use `find <src> -name '*.<ext>' -exec wc -l {} +` or equivalent. Top 20 largest with role.
2. Dead code candidates. Run `vulture <src>` (Python) / `ts-prune` (TS) / `staticcheck` (Go).
   6-gate verification: grep, dynamic import, entry point, reflection, public API, tests.
   Pass all 6 → "deletable". Any miss → "report only".
3. Duplication hotspots. Same logic N≥3 places. Cite file:line for representative.
4. Test coverage gaps. Top 10 production modules with no corresponding test file.

Output:
| File | Lines | Role | Note |   (sizes)
- Deletable: file:line — symbol — 6-gate result
- Report-only: file:line — symbol
| Pattern | N occurrences | Representative |   (dup)
| Module | Risk P0/P1/P2 |   (test gaps)

FORBIDDEN: architecture critique, doc inventory, fix proposals.
```

## W2 — Docs inventory (Explore)

```
Scope (only):
1. Full .md inventory. `find . -name '*.md' -not -path './node_modules/*' -not -path './.venv/*'`.
   Count + distribution by directory.
2. Deletion candidates. Anything with "RESOLVED"/"DONE"/"shipped" status; auto-generated
   directories (e.g., docs/modules/, .planning/); vault-builder artifacts.
3. Wiki-tree violations. Depth > 3; same topic split across multiple subfolders;
   stale CLAUDE.md stubs (>1 line of non-link content).
4. README staleness. Sample 5 commands in root README; verify each file/path exists.

Output:
- Total N. By directory: ...
| Path | Reason | mtime |   (deletion)
- Topic — duplicate locations — recommended merge
- Command — actual vs documented diff

FORBIDDEN: code critique, architecture eval, fix proposals.
```

## W3 — Architecture / interface depth (Plan)

```
Project layer convention: <Clean Arch / hexagonal / MVC / etc — state if known>.
Module size rule: <project-specific, e.g., ≤500>.

Scope (only):
1. Layer boundary violations. Wrong-direction imports
   (e.g., domain → infrastructure). Cite N offending imports.
2. Interface depth. Sample N modules. Classify "thin wrapper" vs "deep self-contained".
   Composer / orchestrator: single procedural pipeline vs dispatch maze?
3. Abstraction justification. Each Strategy/Factory/Adapter/Registry — is it pulling
   weight or yagni? Solo-dev / small-team context = NO multi-region scaffolding,
   feature-flag systems, K8s-only-for-future flexibility.
4. AI-navigability. Cold LLM entering repo — entry point clear? Module-level
   CLAUDE.md self-contained or external-vault redirect?

Output:
- Layer verdict + violations cited
- Deep:shallow ratio + samples
- Justified vs over-engineered abstractions
- Navigability score 0-100 + entry path
- Top 3 95+ gaps

FORBIDDEN: dead-code counting, doc inventory, explicit fix code.
```

## W4 — Adversarial general (Codex)

```
PROJECT CONTEXT: <repo summary>.
OTHER WORKERS: structural, doc, architecture, test, perf, prompt, config, drift, surface.
You are SECOND OPINION. Find blind spots they miss.

Scope (only):
1. Hidden complexity. Surface-clean but mental-model-breaking patterns.
   Same data renamed 5×, 3-layer pass-through that each pass size lint, etc.
2. Type-safety reality. `# type: ignore` count + risk classification.
   `Any` leak hotspots. `cast()` overuse. Decorators that erase types.
3. Test false safety. Tests claiming "end-to-end" with mocks; smoke tests
   marked skip-by-default; monkeypatch path wrong-but-passing.
4. Validator band-aid. Post-hoc regex/numeric extraction from prose; in-place
   mutation pre-validation; "fix" that masks LLM bugs instead of preventing them.
5. Hidden coupling. String-based config switching, global state, import-time
   side effects, env vars read in 10 places without single-source.

Output:
- Each section with cited file:line. Each finding rated P0/P1/P2.
- Final 95+ estimate (0-100) + top 3 risks.

FORBIDDEN: duplicating structural/architecture inventory other workers do.
```

## W5 — Test architecture (Explore)

```
Scope (only):
1. conftest sprawl. Count, total lines, duplicate fixtures, scope misuse.
2. Mock/patch correctness. `from X import Y` patched at definition site (correct)
   vs import site (broken). Cite violations.
3. Test file sizes. Top 10. Flag >1000 line files.
4. Classification. unit / integration / smoke / e2e ratio.
   False-integration (mocked but named "integration").
5. Skip/xfail patterns. Count + classify permanent vs conditional.

Output:
- conftest summary
- Patch violations (file:line)
- Big test files table
- Classification %
- Skip count + permanent suspects

FORBIDDEN: production code critique, fix proposals.
```

## W6 — Performance / infra fit (Plan)

```
Infrastructure context: <e.g., single t3.medium EC2 / k8s / serverless>.

Scope (only):
1. External call count per request/job. Cite path; identify parallelization gaps.
2. Async correctness. `await in loop` without gather; serialization on hot path.
3. Cache patterns. `@lru_cache` on RPC-derived data (memory-leak risk under long-running
   processes). Stale-cache risks.
4. DB efficiency. N+1 patterns, unbounded `IN` lists, materialize-then-filter.
5. Infra overkill. K8s/multi-region/feature-flag scaffolding incompatible with
   stated team size + infra. Cite or "none".

Output:
- RTT count per unit work + reducible
- Async violations
- Cache risk inventory
- DB inefficiency cited
- Overkill cited or none
- Top 3 bottlenecks

FORBIDDEN: code size, dead code, doc inventory.
```

## W7 — Adversarial domain (Codex)

```
DOMAIN: <project-specific — LLM pipeline / ML model / frontend bundle / API service>.

Scope (only) — domain-specific. Examples:

For LLM/prompt-driven projects:
1. Prompt sprawl + dead sections + token waste.
2. Prompt-only rules that should be in validator/schema.
3. Schema-prompt alignment violations (e.g., prompt allows "Pass" enum value
   but schema enum lacks it).
4. Validator band-aid in domain layer.
5. Prompt-cache optimality (static prefix order, dynamic-var placement).

For ML model projects: data leakage, train-test contamination, eval drift, hyperparam sprawl.
For frontend: bundle size, hydration cost, render thrash, dead components.
For API services: contract drift between OpenAPI and impl, missing idempotency,
  pagination consistency.

Output:
- Each finding cited file:line with severity.
- Domain layer score 0-100.
- Top 3 risks.

FORBIDDEN: generic code/arch findings other workers cover.
```

## W8 — Config / env / security (Explore)

```
Scope (only):
1. env var direct reads (`os.getenv`, `process.env.X`). Count + location.
   Single-source violations (project should have one settings module).
2. Config module structure. List of config files + size + role.
3. Secrets in repo. `git grep` for api_key/token/password patterns excluding .md.
   `.gitignore` coverage of .env*.
4. `.env.example` completeness. Compare actual `getenv` keys vs example file.
5. Env-bool parser consistency. Single helper or 10 different truthy patterns?

Output:
- Direct reads N (cited) + single-source violations N
- Config inventory
- Secrets verdict + .gitignore status
- Missing env vars in .env.example
- env_bool bypass cited or none

FORBIDDEN: code critique, doc critique.
```

## W9 — Git / memory drift (general-purpose)

```
Scope (only):
1. Recent 30 commits. Sample 5 — verify claim matches diff.
   `git show <hash> --stat`.
2. Memory file (`MEMORY.md` / `CLAUDE.md` "Resolved" section) — sample 5 claims,
   verify with grep/file size in current code.
3. "Active deferred" pointers — file/line citations actually correct?
4. TODO/FIXME inventory. Count + age via `git blame`. >6 months = stale debt.

Output:
- Commit claim match table
- Memory verification (PASS/STALE per claim)
- Active-deferred citation accuracy
- TODO age distribution
- Memory reliability score 0-100

FORBIDDEN: code size, perf, arch.
```

## W10 — Public API / naming / shallow modules (Plan)

```
Scope (only):
1. `__init__.py` / barrel file re-export. Top 5 by line count.
   Re-export of private (`_`-prefixed) symbols.
2. Public/private boundary. Underscore-prefixed module/symbol used from outside?
   `_foo` imported in N external files = boundary lie.
3. CLI surface bloat. List CLI args + verify each is read by code (not stored-and-ignored).
4. Naming consistency. Same family with mixed conventions
   (e.g., `_tool_player_bs.py` baseball vs `_tool_player_bk.py` basketball — what's the rule?).
5. Shallow modules. Files <30 lines that are just pass-through wrappers,
   alias classes with empty body, single-trivial-function modules.

Output:
- __init__.py table + re-export abuse
- Boundary violations N + cited
- Dead CLI flags
- Naming inconsistencies cited
- Shallow modules listed
- Surface score 0-100 + top 3 ergonomics issues

FORBIDDEN: dead code, perf, doc.
```

---

## Dispatch pattern (tmux + Agent)

The PM session does NOT itself spawn tmux panes — instead, it uses the `Agent` tool with `run_in_background: true` for each worker. Each Agent invocation is a separate sandboxed subprocess; the runtime handles scheduling.

**One message, 10 tool blocks**:

```python
# pseudocode shape; actual is one Agent block per worker
Agent(description="W1 code size", subagent_type="Explore", prompt=W1_PROMPT, run_in_background=True)
Agent(description="W2 docs",       subagent_type="Explore", prompt=W2_PROMPT, run_in_background=True)
Agent(description="W3 arch",       subagent_type="Plan",    prompt=W3_PROMPT, run_in_background=True)
Agent(description="W4 adversarial",subagent_type="codex:codex-rescue", prompt=W4_PROMPT, run_in_background=True)
Agent(description="W5 test",       subagent_type="Explore", prompt=W5_PROMPT, run_in_background=True)
Agent(description="W6 perf",       subagent_type="Plan",    prompt=W6_PROMPT, run_in_background=True)
Agent(description="W7 domain",     subagent_type="codex:codex-rescue", prompt=W7_PROMPT, run_in_background=True)
Agent(description="W8 config",     subagent_type="Explore", prompt=W8_PROMPT, run_in_background=True)
Agent(description="W9 drift",      subagent_type="general-purpose", prompt=W9_PROMPT, run_in_background=True)
Agent(description="W10 surface",   subagent_type="Plan",    prompt=W10_PROMPT, run_in_background=True)
```

**Why not literal tmux**: tmux sessions don't survive between Claude Code turns and don't return structured results. The `Agent` tool's background mode is the equivalent — N concurrent subprocesses, each completes asynchronously, results pushed back as task notifications. Treat it as "tmux for agents".

**If user explicitly requests tmux** (e.g., they want to watch live): use `scripts/tmux-launcher.sh` (see below) which opens 10 panes each running `claude -p <prompt>` or `codex exec <prompt>`. Output captured to per-pane log files, PM tails them. This is slower (no result-push) but visible.

## Result-collection pattern

PM doesn't poll. Background `Agent` tool emits task-notification system messages on completion. PM treats each notification as "worker N done, save snippet, continue waiting". After ≥8 complete (~80% to mitigate stragglers), start Phase 2 synthesis with what's available; late-arriving findings get appended in a re-pass if material.

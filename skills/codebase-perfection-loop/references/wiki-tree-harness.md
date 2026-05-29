# Wiki-tree harness structure

The `.claude/` tree is the **single source of truth** for everything an AI agent or new engineer needs to understand the codebase. No external vault, no Notion, no Confluence — it all lives in the repo, version-controlled with the code.

## Layout

```
CLAUDE.md                       (root, ≤80 lines, INDEX only)
README.md                       (≤100 lines, user-facing entry)
.claude/
├── rules/
│   ├── forbidden-actions.md         # things never to do
│   ├── deployment-safety.md         # push/deploy guard rails
│   ├── verification-methodology.md  # pre-flight before claiming "bug found"
│   └── quality-bar.md               # what 95+ means here
├── architecture/
│   ├── system-overview.md           # 1-page map: data → process → output
│   ├── layers.md                    # Clean Arch / hexagonal layer rules
│   ├── pipeline.md                  # the hot-path flow (one diagram + entry pointers)
│   ├── deep-modules.md              # Ousterhout's deep-module doctrine in this repo
│   └── interfaces.md                # public surface contract
├── runbooks/
│   ├── (per-incident-type).md       # one file per known failure mode
│   └── error-tree.md                # which symptom → which runbook
├── branding/
│   ├── context.md                   # 1-dev / small-team / single-EC2 / etc.
│   ├── scope.md                     # what we DO and DO NOT build
│   └── anti-overengineering.md      # the explicit doctrine
└── prompts/  (only if LLM-driven project)
    ├── base-rules.md
    ├── ko-style.md / en-style.md
    └── per-feature-additions.md

src/**/CLAUDE.md                # 20-40 line self-contained module overview
                                # NO external vault redirect
                                # contains: purpose, public surface, key invariants
```

## Style rules

**Top-level pages are abstract + concise**. Each link drills into detail. Max depth 3 from `CLAUDE.md`.

**Page length cap**:
- Root `CLAUDE.md`: 80 lines
- `README.md`: 100 lines  
- `.claude/*/index.md` or top page: 60 lines
- `.claude/*/<detail>.md`: 200 lines
- Module-level `CLAUDE.md` (`src/x/CLAUDE.md`): 40 lines

Longer than cap → split into subfolder with index.

**No prose narration**. Tables, bullet lists, short sentences. Lead with the rule/fact, then 1-line why.

**No "we will / we should / TODO"**. Docs describe what IS, not aspirational plans. Plans go in PRs/issues.

**Every claim is verifiable from code**. Reader should be able to grep/read to confirm any statement.

**Every cross-reference is a relative link**. `[layers](./layers.md)`. No bare slugs that break under refactor.

## Templates

### Root CLAUDE.md template

```markdown
# <Project Name>

<1-sentence what-this-project-does>

## Quickstart

\`\`\`bash
# install
<one command>
# test
<one command>
# run
<one command>
\`\`\`

## Index

- [Architecture](.claude/architecture/system-overview.md) — system map, layers, pipeline
- [Rules](.claude/rules/) — forbidden actions, deploy safety, verification
- [Runbooks](.claude/runbooks/) — incident response per failure mode
- [Branding](.claude/branding/context.md) — team scale, infra, scope doctrine
- [Prompts](.claude/prompts/) — LLM rules (if applicable)

## Hard rules (3-5 max)

- <rule 1, 1 line>
- <rule 2>
- <rule 3>

## Tech stack

<one line per: language, key frameworks, DB, infra>
```

### .claude/architecture/system-overview.md template

```markdown
# System Overview

## The hot path

```
<step 1> → <step 2> → <step 3> → <output>
```

## Entry point

`<path/to/main.py>` → `<function>` → see [pipeline](./pipeline.md)

## Layers

- **Domain** (`src/domain/`) — pure logic, no I/O
- **Application** (`src/application/`) — orchestration
- **Infrastructure** (`src/infrastructure/`) — I/O adapters
- **Interface** (`src/interface/`) — CLI / HTTP / SDK boundary

Detailed rules: [layers](./layers.md). Deep-module doctrine: [deep-modules](./deep-modules.md).

## Storage / external services

- <DB name> — <purpose>
- <External API> — <purpose>

## Test command

\`\`\`bash
<command that runs all tests>
\`\`\`
```

### .claude/branding/anti-overengineering.md template

```markdown
# Anti-overengineering doctrine

## Context

- Team size: <N developers>
- Infrastructure: <e.g., single EC2 t3.medium, supabase>
- Scale: <e.g., <10k requests/day>

## What we don't build

- **Multi-region anything** — we have one region. Adding HA scaffolding is yagni until SLA forces it.
- **Feature flag systems** — env vars + a 5-line helper is the whole flag system.
- **Microservices** — one repo, one process, one DB until pain forces split.
- **Abstract base classes for "future flexibility"** — concrete code first. Abstract when 3rd implementation appears.
- **Caching layers without a measured hot path** — add cache when profiler shows it; not before.

## What we DO build

- Tests (the safety net we keep)
- Linters / formatters in CI
- Single observable log stream
- One deployment script

## Test before abstraction

"Three similar lines is better than a premature abstraction." Wait until 3 callsites
exist before extracting; then extract the minimal abstraction those callsites actually need.
```

### Module-level CLAUDE.md template (`src/x/y/CLAUDE.md`)

```markdown
# <module name>

<1-sentence purpose>

## Public surface

- `public_function_a(x: T) -> U` — <what it does>
- `PublicClass` — <what it represents>

## Internals

- `_internal_helper` is private to this module; do not import from outside.

## Invariants

- <something the module guarantees, e.g., "returns normalized output">
- <another invariant>

## Test command

\`\`\`bash
pytest src/tests/<corresponding-test-path>
\`\`\`

## Related

- Calls into [<other module>](../other/CLAUDE.md)
- Called from [<caller module>](../../caller/CLAUDE.md)
```

## What gets DELETED

Phase 5 cleanup nukes (with user consent):

- `docs/` (except auto-generated module reference if any — gitignore it)
- `docs/modules/`, `docs/notebook-sources/` — usually auto-generated
- `.planning/` — workflow artifacts
- `.vault-builder/` — vault-builder drift output
- Anything in `docs/plans/` marked RESOLVED/DONE
- Stale ADRs (move to `.claude/architecture/decisions/` only if still load-bearing)

Add to `.gitignore`:
```
docs/modules/
.planning/
.vault-builder/
```

## Wiki-tree depth check

Run this after Phase 5 to verify no over-nesting:

```bash
find .claude -name '*.md' | awk -F/ '{print NF, $0}' | sort -rn | head -5
```

Top result should be ≤5 slashes (`.claude/<subtree>/<detail>.md` = 4). If any path is deeper, flatten.

## Link integrity check

```bash
# all relative .md links resolve
grep -rno '\[.*\](.*\.md)' .claude CLAUDE.md README.md \
  | while IFS= read -r line; do
      file=$(echo "$line" | cut -d: -f1)
      target=$(echo "$line" | grep -oE '\([^)]+\.md\)' | tr -d '()')
      dir=$(dirname "$file")
      [ -f "$dir/$target" ] || echo "BROKEN: $line"
    done
```

Run this in Phase 5 verify-step. Zero broken links = release.

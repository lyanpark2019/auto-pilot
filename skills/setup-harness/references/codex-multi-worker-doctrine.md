# Codex Multi-Worker Analysis — Doctrine

> 15 principles + 12 sources for running an Opus-PM + Codex-worker supervisor pattern. Companion to `scripts/codex-analyze.sh` and `templates/wiki-harness-engineering/`.

Synthesised 2026-05-15 from two NotebookLM notebooks (39 sources): "Harness Engineering — Claude Code & Codex" (3c01cb29) + "Harness Engineering" (5b5fb594). Validated end-to-end on a Python codebase (5 workers × 9 min avg, 956 lines structured output, 968 lines vault publish).

## Definition

> "Harness engineering is the practice of configuring the environment, rules, and tools around a coding agent to improve its reliability." — HumanLayer (coined term).

Three sibling disciplines:

| Discipline | Layer | Breaks on |
|------------|-------|-----------|
| Prompt engineering | Language | Multi-turn autonomous tasks |
| Context engineering | Information | Behavioural governance needed, not knowledge |
| **Harness engineering** | **Autonomy** | (this is the envelope) |

## A. Supervisor (PM) + Worker pattern

### P1 — Hierarchical fan-out / fan-in
Supervisor (Opus) decomposes work, dispatches to N workers (Codex), synthesises. Empirical 4.3× wall-clock speedup vs serial; ~9 min/worker for layer-scale analysis at xhigh effort.  
*Source*: Claude Code Advanced Course.

### P2 — Model diversity
Mix model families (Opus PM + Codex worker). Monoculture failure mitigation.  
*Source*: "NEW Hidden Features You MUST Enable".

### P3 — Worker context isolation (context firewall)
Worker reads only its scope. PM receives summary, not raw transcripts. Prevents "context rot".  
*Source*: Paradime guide.  
*Implementation*: `inbox/worker-N/` + `outbox/worker-N/` isolated directories.

## B. Multi-pane tmux operation

### P4 — Worktree per worker (when writing)
Parallel write-mode workers own separate git worktrees. Read-only analysis can share repo main.  
*Source*: kylestratis "Better Practices".

### P5 — Human-in-loop round robin
Operator cycles panes to approve permission prompts. Don't idle while workers wait.  
*Source*: kylestratis "Better Practices".

## C. File-based message bus

### P6 — Repository filesystem is the memory layer
LLM sessions are stateless across resumes. Every plan, ticket, progress note lives in versioned files.  
*Source*: OpenAI "Harness engineering"; "Turn Claude Code into Engineering Team".  
*Anti-implementation observed*: `codex-companion --background` broker state is process-local and NOT round-trippable from a fresh CLI invocation. Use `codex exec` sync mode + Claude `run_in_background` instead.

### P7 — Progressive disclosure
Root CLAUDE.md is a table of contents. Deeper references load only when needed. Protects attention budget.  
*Source*: HumanLayer "Writing a good CLAUDE.md"; Paradime.

## D. PM brief / review

### P8 — Upfront intent + verifiable success criteria
TDD-style or path/line-level scoped tickets. No "be careful" or "do your best".  
*Source*: kylestratis; OpenAI harness blog.

### P9 — Adversarial, fresh-context QA
Authoring agent does not review own output. Fresh agent without confirmation bias.  
*Source*: kylestratis; Claude Code Advanced Course.

### P10 — Mechanical back-pressure
Linter, hook, deterministic test reject bad code. "Success is silent."  
*Source*: OpenAI harness blog; Paradime.  
*Connects to*: `score-harness.sh` 15 dim, `verify-harness.sh` functional hook tests, `references/hook-templates.md`.

## E. Philosophy

### P11 — Simple loop + atomic tools
Anthropic view. `while True: read; act; observe.` over elaborate DAGs.  
*Source*: "How Claude Code Works" — Jared Zoneraich, PromptLayer.

### P12 — RPI workflow (Research / Plan / Implement)
Dex Horthy. Compress long output to succinct markdown between phases. Keep agent in "smart zone".  
*Source*: HumanLayer "No Vibes Allowed".

### P13 — Context-as-code lifecycle
Patrick Debois (Tessl). Generate → evaluate → deploy → observe context.  
*Source*: "컨텍스트가 새로운 코드입니다 — Tessl".

### P14 — Reasoning thread on PR
Mitchell Hashimoto. Append plan + execution log to PR description.  
*Source*: HumanLayer "No Vibes Allowed".

## F. Anti-patterns

### P15 — The Forbidden Five
1. **Vague constraint** ("be careful") → silent corruption. Use machine-readable laws.
2. **Self-verification** → echo chamber. Independent validator only.
3. **Over-constrain ↔ under-constrain** → paralysis or blast radius. Calibrate to test coverage + reversibility.
4. **No ralph-loop** — deterministic test failures must feed back automatically.
5. **No deterministic gate before PR review** — humans should never burn cognitive cost on machine work that hasn't passed structural tests.

*Source*: "Why Prompt Engineering Is Dead 2026"; Ai++ "One Million Lines"; OpenAI harness blog.

## Source catalogue

| Key | Source | Core message |
|-----|--------|--------------|
| H1 | OpenAI "Harness engineering" blog | Definition + envelope |
| H2 | OpenAI "Unlocking the Codex harness: App Server" | Broker / thread / job abstraction |
| H3 | HumanLayer "Writing a good CLAUDE.md" | ToC pattern; progressive disclosure |
| H4 | Paradime guide | Skills + plugins + MCP map |
| H5 | kylestratis "Better Practices" | Worktree + human-in-loop |
| H6 | "No Vibes Allowed — Dex Horthy" | RPI; PR reasoning thread |
| H7 | "One Million Lines — Ai++ Ep 6" | Ralph-loop; deterministic gates |
| H8 | "Why Prompt Engineering Is Dead 2026" | Constraint calibration; red-teaming |
| H9 | Patrick Debois (Tessl) | Context-as-code lifecycle |
| H10 | Anthropic "Don't Build Agents, Build Skills" | Skill packaging |
| H11 | "How Meta Used AI to Map Tribal Knowledge" | Tribal knowledge → vector index |
| H12 | Stanford CS230 Lec 8 | Academic baseline for agents/RAG |

## Two dispatch modes (both valid; pick per session)

| Aspect | Mode A: Claude `run_in_background` | Mode B: tmux pane |
|--------|-----------------------------------|-------------------|
| PM identity | this Claude Code session | operator at pane 0 |
| Dispatch call | `codex-analyze.sh dispatch <ticket>` × N | `codex-analyze.sh spawn <root>` once, then drop tickets into inbox/worker-N/ |
| Worker invocation | direct `codex exec` per Bash call | `worker-loop.sh` polls inbox + invokes `codex exec` |
| Completion signal | Claude turn notification (auto) | Operator reads pane / outbox file |
| PM session crash | risk — Claude reparent may lose tracking | safe — tmux session detached, workers continue |
| Visual observation | `wc -l outbox/*.md` only | `tmux attach` shows live pane output |
| Outside Claude harness | requires Claude | runs standalone with codex CLI |
| Best for | one-shot batches, automation pipelines, this-session work | long ops, multi-session, human-in-loop observation, operator-driven flow |

**Both call `codex exec` synchronously (stdin → stdout → file). Neither uses `codex-companion --background`.**

## Operational learnings (2026-05-15 first validated runs)

1. **`codex-companion --background` is broken for this pattern.** Returns a job ID but `codex-companion status` from a fresh invocation reports "No jobs recorded yet" — broker state is in-process. **Never call it from the supervisor pattern.** Use `codex exec` sync in both modes A and B.
2. Empty outbox file mid-flight is NOT failure. Codex emits final response only at exit. Check `ps aux | grep "codex exec"` for liveness.
3. Five concurrent `--effort xhigh` codex workers strain OpenAI rate limit but complete. Longest worker = 18 min (largest scope) in the validated run.
4. tmux mode validated 2026-05-16: 6 pane (PM 1 + worker 5), dummy ticket processed in 35s, ticket → done mv, idle panes keep polling. macOS bash 3.2 compatible (no `declare -A`, no `${!ARRAY[@]}`).
5. Apply deletion test + path:line citation gates on every worker output. Workers without these gates produce planning prose, not facts.

## Drivers (operational — moved from SKILL.md 2026-05-25)

When to run this pass: codebase too large for one Opus turn; want layer-by-layer
friction analysis with `path:line` citations; want output published into an
Obsidian vault `wiki/harness-engineering/` tree; model diversity desirable.

Use `codex exec` (sync), NOT `codex-companion --background` (broker job state is
process-local — a fresh CLI invocation cannot read prior job IDs). Worker stdout
is redirected to `.planning/harness-rewrite/outbox/worker-N/<ticket>.md`.

```
Opus PM (this Claude Code session) ── codex exec ─→ Codex worker × 5 (parallel)
        │                                                  │
        ├── ticket JSON per worker                          ├── reads doctrine.md
        ├── outbox review + deletion test + citation gate   ├── reads scope_files
        ├── vault publish gate                              └── writes markdown to outbox
        └── ledger.md (append-only)
```

### Mode A — Claude `run_in_background`

```bash
# 1. Scaffold .planning/harness-rewrite/ + copy doctrine reference
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/codex-analyze.sh init /path/to/project 5
# 2. PM writes 5 ticket JSON into .planning/harness-rewrite/inbox/worker-{1..5}/
# 3. Dispatch all 5 in parallel
for w in 1 2 3 4 5; do
  bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/codex-analyze.sh dispatch \
    /path/to/project/.planning/harness-rewrite/inbox/worker-${w}/01-discover.json &
done; wait
# 4. Verify worker output gates
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/codex-analyze.sh verify \
  /path/to/project/.planning/harness-rewrite/outbox/worker-1
# 5. Publish to vault (after PM gate)
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/codex-analyze.sh publish \
  ~/Documents/Obsidian/<project>-Vault /path/to/project
```

### Mode B — tmux pane

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/codex-analyze.sh init /path/to/project 5
bash ${CLAUDE_PLUGIN_ROOT}/skills/setup-harness/scripts/codex-analyze.sh spawn /path/to/project 5
tmux attach -t harness   # optional: observe live
# PM drops ticket JSON into inbox/worker-N/. Each pane polls ~8s, claims a ticket,
# runs `codex exec` sync, writes outbox/worker-N/<ticket>.md, moves ticket to done/.
# verify + publish identical to Mode A.
tmux kill-session -t harness   # teardown
```

### Worker output gates (enforced by `codex-analyze.sh verify`)

| Gate | Threshold |
|------|-----------|
| YAML frontmatter | first line `---` |
| Markdown size | ≥ 30 lines |
| Citation count | ≥ 5 `path:line` matches |
| Wikilinks | recommended ≥ 5 |
| Deletion test | each paragraph must claim something whose removal loses information |

### Empirical (first validated run, 2026-05-15)

- 5 workers × `--effort xhigh` sync = 9–18 min/worker by scope
- Phase 1 (01-discover): 515 lines structured analysis
- Phase 2 (02-draft): 441 lines Obsidian-compatible vault pages
- Publish: 11 vault pages, 968 lines, all citation + wikilink gates pass

### Tree produced

```
.planning/harness-rewrite/
├── refs/{doctrine.md, friction-map.md}
├── inbox/worker-{1..5}/   (PM writes tickets)
├── outbox/worker-{1..5}/  (workers write markdown)
├── done/worker-{1..5}/    (consumed tickets archived)
├── pm-draft/              (PM-authored vault pages)
└── ledger.md              (append-only PM log)

~/Documents/Obsidian/<project>-Vault/wiki/harness-engineering/   ← publish target
├── index.md
├── principles/{01-doctrine,02-supervisor-pattern,03-message-bus}.md
├── layers/{interface,application,domain,infrastructure,cross-cutting}.md
├── deepening-backlog.md
└── friction-map.md
```

### When NOT to use

- Single-file edits → one Opus session
- Already documented at this fidelity → run `harness-loop.sh` (incremental)
- No Codex CLI → fall back to `Agent(subagent_type=Explore)` × N
- Cost-sensitive → drop effort to `high` or worker count to 3

Templates: `templates/wiki-harness-engineering/` (README spec + index/principle/layer
skeletons; PM customises `{{PROJECT_NAME}}`, `{{DATE}}` placeholders).

## Cross-references inside setup-harness

- `references/measuring-harness.md` — 15 dim scoring
- `references/hook-templates.md` — mechanical back-pressure (P10)
- `references/prohibition-patterns.md` — anti-patterns (P15)
- `scripts/codex-analyze.sh` — implementation of this doctrine
- `templates/wiki-harness-engineering/` — vault publish skeleton

# vault-builder

> Unified autonomous Obsidian vault builder. Pluggable source adapters → vault with rubric-driven PM-Worker-Ticket loop until pass.

## Scope

Single global plugin at `~/.claude/plugins/vault-builder/`. Subsumes three predecessors:

| Predecessor | Pattern | Now |
|---|---|---|
| `notebooklm-vault-builder` (plugin) | NotebookLM workspace → vault | `--source notebooklm` |
| `autonomous-docs-loop` (skill) | code → module docs vault | `--source code` |
| `sportic365-API make kb-update` (repo) | code + git + sentry + gh + supabase | `--source api_kb` (adapter pending) |

Old triggers still work via the `/nbm-to-obsidian` backward-compat alias (`/autodocs` removed 2026-06-05 — use `/vault-build --source code`).

## Quickstart

```bash
# NotebookLM → vault (replaces /nbm-to-obsidian)
/vault-build --source notebooklm ~/Documents/Obsidian/MyVault

# Code → docs vault
/vault-build --source code ~/Documents/Obsidian/CodeDocs --input ~/Project/MyRepo

# Dry-run (Phase 1.5 only)
/vault-build --source code ~/v --input ~/Project/MyRepo --dry-run

# Override rubric
/vault-build --source code ~/v --rubric ./custom-rubric.yaml
```

## Architecture

```
vault-builder/
├── sources/                            # input adapter
│   ├── _adapter.py                     # protocol + registry
│   ├── notebooklm.py                   # NotebookLM CLI → notebooks
│   ├── code.py                         # CWD scan → modules
│   └── api_kb.py                       # repo + collectors (TBD)
├── pipeline/
│   ├── loop.py                         # 7-phase driver
│   └── state.py                        # unified state JSON + legacy migration
├── agents/                             # 26 agents
│   ├── pm-orchestrator.md              # opus, source-aware modes
│   ├── docs-worker.md / docs-verifier.md  # code-source pair
│   ├── adversarial-auditor.md / content-fact-checker.md
│   └── 21 specialized workers/         # density-booster / concept-populator / ...
├── rubrics/                            # library
│   ├── notebooklm.yaml                 # 17 dim, 100/100
│   ├── code-docs.yaml                  # 6 dim, 95+
│   └── _user/                          # user overrides
├── scripts/                            # 11 utilities (kernel)
│   ├── ticket_system.py / cost_tracker.py / lockfile.py / worker_backup.py
│   ├── score_structural.py / score_content.py
│   ├── selftest.py / dashboard_data.py / mcp_vault_server.py
│   └── pm_loop.py / wiki_ingest_chain.py
├── commands/                           # 10 commands
│   ├── vault-build.md                  # unified entry
│   ├── nbm-to-obsidian.md                # legacy alias
│   ├── vault-drift.md                  # drift detector report
│   └── vault-score / vault-audit / vault-content-verify / vault-resume / vault-dashboard / vault-selftest
├── hooks/                              # 3 hook scripts + hooks.json
├── tests/                              # 59 tests (pytest)
├── dashboard/                          # zero-dep HTML
├── templates/                          # rubric.yaml shared default + _TEMPLATE_worker.md (boilerplate)
├── .claude-plugin/                     # plugin.json + marketplace.json
├── .mcp.json                           # MCP server registration (notebooklm-vault)
├── .gitignore
├── LICENSE                             # MIT
├── CHANGELOG.md
└── README.md
```

## Source adapter protocol

```python
class SourceAdapter(Protocol):
    name: str
    default_rubric: str

    def discover(self, input_path, **opts) -> list[SourceItem]: ...
    def classify(self, items, **opts) -> dict[str, list[SourceItem]]: ...
    def bootstrap(self, vault, buckets, **opts) -> None: ...
    def materialize(self, vault, buckets, **opts) -> None: ...
    def plan_tickets(self, vault, round_num, score_state, **opts) -> list[TicketPlanEntry]: ...
```

Adapters auto-register via `@register` decorator. Add a new one by:

1. Drop `sources/myname.py` implementing protocol
2. `@register` decorate the class
3. Add `rubrics/myname.yaml`
4. Use via `/vault-build --source myname`

## Pipeline phases

1. **Discover** — adapter lists source items
2. **Classify** — bucket into categories
3. **Bootstrap** — vault directory tree per category
4. **Materialize** — write raw content (download/scan)
5. **PM loop** — pm-orchestrator dispatches workers (source-aware mode)
6. **Audit** — adversarial-auditor every 2 rounds; content-fact-checker after pass
7. **Done** — vault verified + unified state finalized

## Unified state file

`<vault>/meta/vault-builder-state.json`:

```json
{
  "schema_version": 1,
  "vault": "/abs/path",
  "source_adapter": "notebooklm",
  "round": 3,
  "scores": {
    "structural": {"total": 100, "scores": {...}},
    "content": {"total": 100, "scores": {...}}
  },
  "tickets": {"T-R1-density-...": {...}},
  "audits": ["audit-r2.md", "audit-r4.md"],
  "phases": {"discover": {"items": 93}, "classify": {"buckets": {...}}, ...}
}
```

Legacy state files (`score-state.json`, `score-content-state.json`, `ticket-state.json`, `~/.claude/state/<project>-docs.json`) auto-migrated via `pipeline/state.py::migrate_legacy`.

## Verified status

| Source | Dogfood | Score | Tests |
|---|---|---|---|
| notebooklm | `~/Documents/Obsidian/NotebookLM-Archive` (93 notebooks, 7 cats) | struct 100/100 + content 100/100 (no regression after migration) | 59/59 pytest |
| code | `~/Documents/Project/EC2` dry-run: admin(127) + db(148) + scripts(3) | (PM loop pending; phase 1.5 verified) | adapter tests |
| api_kb | (deferred — sportic365-API binding) | — | — |

## Cost mode

`rubrics/*.yaml > cost.mode`:
- `subscription` (default) — Claude Code Pro/Max quota covers Agent dispatch. No $ gate.
- `api` — meter against per-1M token prices. PM aborts on budget exceeded.

Token usage logged either way (audit trail).

## Backward compatibility

Old plugin `notebooklm-vault-builder` (v0.6.0) stays installed. Both can coexist; `vault-builder` supersedes. To remove old:
```bash
mv ~/.claude/plugins/notebooklm-vault-builder ~/.claude/plugins/_archive-notebooklm-vault-builder
```

Old skill `~/.claude/skills/autonomous-docs-loop/` stays. Same archive procedure.

## License

MIT

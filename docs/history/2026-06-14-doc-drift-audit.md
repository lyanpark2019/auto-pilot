---
type: history
topic: doc-drift-audit
date: 2026-06-14
baseline_commit: 1664e87
manual_edit: true
---

# Doc/comment drift audit — 2026-06-14 (per-folder)

Exhaustive per-folder audit of every doc claim + code comment vs current code
(graphify 0.8.35 + Read/Grep), adversarially verified. 11 areas, 55 audit/verify
agents, 43 confirmed findings → **41 auto-fixed + 2 manual + 1 size-condense**.
**0 P0** (no actively-misleading current-behavior errors). Baseline `1664e87` (#64).

## Per-folder status

| Area | Health | Confirmed | Notes |
|------|--------|-----------|-------|
| `docs/` | GOOD | 4 | dead `docs/plans/` ref removed; `_promotion.py` cite 32→138; asset-charter Round-5 snapshot |
| `skills/` | HIGH | 3 | codex-analyze subcmd list (+`spawn`); dead `check_doc_source_refs.py`→`check_doc_reference_integrity.py` |
| `agents/` | GOOD | 4 | stale `file:line` cites (pm-orchestrator, vault-*) — not covered by `docs:check` guard |
| `commands/` | LOW-MOD | 6 | dead `--allow-dirty` flag; wrong exit-code; `--restructure` phase + selftest counts |
| `hooks/` | LOW | 3 | state-write-guard role-list comment; context-watch token-method comment |
| `scripts/` | LOW-MOD | 8 | CLAUDE.md module table +8 rows; dead-symbol docstring refs |
| `swarm/` | MIXED | 7 | pre-merge proposal docs (merge-lock, tmux-kill-switch) stale vs grown scripts |
| `vault/` | GOOD | 2 | export.py docstring (un-impl removal); stale invocation example |
| `codex/` | CLEAN | 0 | zero drift — fork count, licenses, sync semantics all verify |
| root (`CLAUDE.md`/`README`) | VERY LOW | 4 | module table, layout bullets (codex/deploy/dashboard/evals split), state-write-guard role list, shellcheck matcher |
| `evals/`+`prompts/`+`tests/`+`schemas/` | LOW | 4 | stale `tests/README.md` + `evals/README.md`; schemas guarded by tests |

## Regression caught + fixed in-loop

The `docs/architecture.md` promotion-CLI cite fix (line 32→138) tripped the
mechanical citation guard — its nearby-symbol heuristic mis-coupled a conceptual
`` `class` `` backtick on the adjacent Inputs bullet to the CLI citation. Resolved by de-backticking the
conceptual `class` (consistent with neighboring "class-level"/"per-class" plain
usage). `orchestrator.py` Usage-docstring growth (+6) breached its 595 size budget
→ condensed net-neutral.

## Residuals (deferred, out of surgical scope)

- `skills/doc-management/references/doc-management-system.md:70` dead `check_doc_source_refs.py` ref — path is in `.claude/human-only.paths`; needs a human edit (not agent/bash-bypass).
- `docs/asset-charter.md:25` — 3 stale table-cell `file:line` cites; file is auto-generated (`manual_edit:false`). Needs the charter generator regen, not hand-edit. Interim: a Round-5 live-count snapshot was appended.

## Gates (post-fix)

pytest pass · ruff · mypy (66) · module-size · doc-reference-integrity 0 violations
· hook self-tests · shellcheck · bats (setup-harness + ARL).

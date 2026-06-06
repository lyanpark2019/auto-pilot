---
description: Autonomous Obsidian + NotebookLM restructure loop. Backs up existing vaults, renames to <project>-Vault convention, merges sportic365 duplicates, splits NotebookLM-Archive into per-domain vaults, creates skeletons for missing domains, emits vault-build + notebooklm-create manifests. Idempotent + resume-safe via state file.
argument-hint: "[--dry-run] [--phase N] [--reset] [--verify-all]"
allowed-tools: [Bash, Read]
---

# /vault-restructure

Single-command autonomous restructure of `~/Documents/Obsidian/` per the project ↔ vault ↔ NotebookLM mapping in `scripts/restructure_phases/_mapping.py`.

## Usage

```bash
# Simulate every phase, no side effects (recommended first run)
/vault-restructure --dry-run

# Live run; resumes from last completed phase
/vault-restructure

# Re-run a specific phase (skips previously-completed earlier phases)
/vault-restructure --phase 3

# Reset state and start over (does NOT delete vaults — only state file)
/vault-restructure --reset

# Re-verify every phase; mark stale ones pending so next run re-executes
/vault-restructure --verify-all

# FULL autonomy: includes Phase 6 — shells out to `claude -p /vault-build`
# per pending domain. Each dispatch capped at $5 (set VAULT_BUILD_BUDGET_USD).
# Total time ~ 10-30 min per domain. Run only when ready.
/vault-restructure --execute-builds
```

## Phases

1. **backup** — `tar czf` every existing vault to `/tmp/obsidian-backups/`
2. **rename_simple** — `CLAI` → `clai-Vault`, `ga4-collector` → `ga4-collector-Vault`, `PickL-Vault` → `pickl-Vault`
3. **sportic365_merge** — `Sportic/` + `SporTic365/` → `sportic365-Vault/_sub-projects/*` + `kbo-reference/` + `_legacy/`
4. **notebooklm_split** — `NotebookLM-Archive/{sportic-projects,match-analysis,pickl-projects,lotto,agri-trade}` → respective domain vaults
5. **new_vault_skeletons** — create `agitrade-Vault`, `fyqro-Vault`, `proto-Vault`, `EC2-Vault`, `EC2-Vault` skeletons + `_index.md`
6. **vault_build_per_domain** — emit `/vault-build` command manifest + score existing vaults
7. **notebooklm_create** — emit `notebooklm create` command manifest

## State

`~/.claude/state/obsidian-restructure-state.json` — read on every run for resume.

## Execution

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/restructure_loop.py "$@"
```

## Verification

- `~/.claude/state/obsidian-restructure-final-report.md` — phase-by-phase summary
- `~/.claude/state/obsidian-restructure-build-manifest.json` — Phase 6 manifest
- `~/.claude/state/obsidian-restructure-notebooklm-manifest.json` — Phase 7 manifest

## Recovery

Phase 1 tarballs in `/tmp/obsidian-backups/` allow full rollback:
```bash
cd ~/Documents/Obsidian
tar xzf /tmp/obsidian-backups/obsidian-backup-Sportic-<date>.tgz
```

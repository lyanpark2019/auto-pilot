---
type: runbook
topic: escalation-agent-loading
manual_edit: true
---

# Runbook — Loading Escalation Agents After Plugin Update

## Problem

The plugin loads from a version-bucketed cache:

```
~/.claude/plugins/cache/auto-pilot-marketplace/auto-pilot/<ver>/
```

The `escalation-resolver` (`agents/escalation-resolver.md`) and
`enrichment-fetcher` (`agents/enrichment-fetcher.md`) agents shipped in
`origin/main` after PR #85 and PR #80 respectively.  If the installed cache
version predates those PRs, the agents are absent and cannot be dispatched
— Claude will report "unknown agent" or silently fall back to a generic role.

See also: `docs/adr/0003-gated-ondemand-enrich-two-tier-escalation.md`

## Steps

1. **Confirm origin/main is the source.**  Either use a fresh checkout or
   ensure your local worktree is tracking the correct remote and is up to date:

   ```bash
   git fetch origin
   git log origin/main --oneline -3
   ```

2. **Reinstall or refresh the plugin at a bumped version.**  The marketplace
   manifest lives at `.claude-plugin/marketplace.json`.  Bump `version` and
   reinstall through Claude Code's plugin manager (Settings → Plugins) or
   run the install command from the plugin directory:

   ```bash
   claude plugin install .claude-plugin/plugin.json
   ```

3. **RESTART the Claude Code session.**  The SessionStart hook reloads the
   agent registry from the cache.  A running session sees the stale cache;
   there is no hot-reload.

4. **Verify the agents are present in the new cache:**

   ```bash
   ls ~/.claude/plugins/cache/auto-pilot-marketplace/auto-pilot/<ver>/agents/ \
     | grep -E 'escalation|enrichment'
   ```

   Expected output includes `escalation-resolver.md` and `enrichment-fetcher.md`.

## Concurrency caveat

Do **not** hard-realign the shared root checkout (`/Users/lyan/Documents/Project/auto-pilot`)
if another session may own it.  A `git checkout` in one session flips the
shared `.git/HEAD`; a concurrent session then silently lands on the wrong
branch and any uncommitted work can be clobbered.  Use a dedicated git
worktree for upgrade operations:

```bash
scripts/ap-worktree.sh new plugin-upgrade
```

Then drive all git operations through `git -C <worktree-path>` and merge via
`scripts/ap-worktree.sh done plugin-upgrade` when complete.

## Cross-references

- `agents/escalation-resolver.md` — resolver agent contract (inc3 Phase 2)
- `agents/enrichment-fetcher.md` — enrichment-fetcher agent contract (inc2 Phase 2b)
- `docs/adr/0003-gated-ondemand-enrich-two-tier-escalation.md` — ADR for the
  two-tier escalation + enrichment design decision

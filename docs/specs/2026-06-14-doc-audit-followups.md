---
type: spec
topic: doc-audit-followups
date: 2026-06-14
baseline_commit: b32c1b4
manual_edit: true
---

# Doc-audit follow-ups — next session

Carry-overs after the 2026-06-14 per-folder doc-drift audit (#65) + residual close (#67).
Baseline `main@b32c1b4`. Ordered by leverage.

## P1 — asset-charter.md is structurally drift-prone (the real debt)

`docs/asset-charter.md` carries **52 `file:line` cites** snapshotted at `36dc75b`, with
**no generator** (`build_dashboard_data.py` emits the dashboard, not the charter — verified).
Only the 3 audit-flagged cites were fixed in #67; the other ~49 are unverified and likely
drift as source files grow. The mechanical guard (`scripts/docs/check_doc_reference_integrity.py`)
does NOT catch them — table-cell cites have no adjacent backtick symbol, so the symbol-proximity
check is skipped → silent drift.

Pick ONE durable fix (do not hand-patch 52 — that's the deny-list whack-a-mole the rules forbid):
- **(a) symbol/section anchors** — replace `path:NNN` with `path#symbol` / section refs (stable across line shifts). Lowest churn, no new code.
- **(b) generator** — make `build_dashboard_data.py` (or a new `scripts/docs/gen_asset_charter.py`) emit `asset-charter.md` from `collect_assets()` + per-asset source lookups; wire into a gate so it stays fresh. More code, fully auto.
- Either way: the file is now honestly `manual_edit: true` (#67). If (b) ships, flip back to `false`.
- Bonus: extend the guard's symbol-proximity to table-cell cites so this can't silently drift again.

## P2 — docs/specs/2026-06-13-next-session-queue.md: 6 stale-symbol WARN

The mechanical guard emits 6 WARN for `docs/specs/2026-06-13-next-session-queue.md`
(`lyanpark2019`, `main`, `_locked_update`, `load_tickets`, `user_approved`, `role`, `task_class`
not found near their cited lines). WARN-only because `docs/specs/**` is exempt by design.
Decide: refresh the cites, OR dispose the spec (per the convention — shipped specs get distilled
into `docs/architecture.md` then deleted; `agents/retro.md` owns disposal). Likely dispose.

## P3 — minor cleanup

- `.claude/worktrees/iter-1`, `iter-2` — orphan auto-pilot LOOP worktree dirs (not registered in
  `git worktree list`). Left untouched this session — a concurrent session held an active worktree
  (`fix/branch-lock-deny-msg`). Verify no active loop, then prune.
- Old local branches `fix/worker-done-verify-gate`, `release/v0.8.9-metadata` — confirm merged
  (`git branch --merged origin/main`) then delete.

## Done this session (for context)
#62 vault mirror_docs auto-sync · #65 doc-drift 43 findings · #67 residual 2 (human-only ref +
asset-charter 3 cites). Gotchas in memory `doc-drift-audit-2026-06-14`.

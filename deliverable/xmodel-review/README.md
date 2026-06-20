# xmodel-review — cross-model adversarial review

A lightweight, usable deliverable: **two models review the same change, you see both opinions.**
One Claude reviewer + one Codex reviewer see the identical diff, each emits an APPROVE/REJECT
verdict with findings, and a merge step prints them side by side with an overall verdict
(REJECT if *either* rejects).

This is the one differentiator that measured out across this project's investigation — and only
in a specific regime (see **Where it helps**). It is built as a **pure Archon workflow** + a thin
runner; there is no learning loop, no plugin, no persistent state.

## Why (and where it helps)

The value is cross-**model diversity**: a second model catches blind spots the first misses.

- **Strong here:** hard reasoning — plans, designs, subtle/complex diffs. In testing, Codex flipped
  a plan verdict another model had marked sound, surfacing 6 real design blind spots it had missed.
- **~0 here:** easy/medium code. A single strong model already saturates (catches everything), so a
  second opinion adds nothing. Don't reach for this on a 10-line bugfix.

This was measured, not assumed. A separate idea tested alongside it — a "learning loop" that injects
a memory of past defect *classes* as a nudge — was **disproven**: it is a no-op for capable reviewers
(they don't fail by forgetting a class), so it is intentionally **not** part of this tool.

## Use

```bash
# review the current repo's uncommitted change (staged + unstaged + new files vs HEAD)
deliverable/xmodel-review/xreview.sh

# review a different repo
deliverable/xmodel-review/xreview.sh /path/to/repo

# review a plan/design doc: stage or write the .md, then run xreview in that repo
```

Output: each model's verdict + findings, then `OVERALL: APPROVE|REJECT|ABSTAIN`. A reviewer that
hits a usage limit or fails is reported as `ABSTAIN` (the other still reports).

## Requirements

- The Archon engine checkout. Default `ARCHON_ROOT=/Users/lyan/Documents/Project/archon`; override
  with the env var. (Archon is the workflow engine — `bun run cli workflow run ...`.)
- Codex auth (`~/.codex/auth.json`) and a logged-in Claude (`CLAUDE_USE_GLOBAL_AUTH=1`, set by the
  runner). The Claude reviewer node runs cleanly inside a Claude Code session (Archon strips the
  nested-session marker).

## Install

```bash
deliverable/xmodel-review/install.sh   # copies xmodel-review.yaml into ~/.archon/workflows/
```

After install the workflow is discoverable from any directory, so `xreview.sh` works on any repo.

## Files

| File | Role |
|---|---|
| `xmodel-review.yaml` | the Archon workflow (source of truth) |
| `xreview.sh` | one-command runner over a target repo |
| `install.sh` | install the workflow into `~/.archon/workflows/` |

## Scope (what this is NOT)

This packages only **cross-model review**. auto-pilot's other subsystems — the Obsidian knowledge
**vault**, **doc-management** (drift audit/guards), **graphify** — are an orthogonal knowledge/docs
layer that Archon does not touch; they stay in auto-pilot as-is and are not part of this deliverable.

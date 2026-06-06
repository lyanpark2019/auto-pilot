<!-- Single source for multi-agent mode validation criteria and anti-patterns.
     Pointer in SKILL.md § multi-agent mode. Do not duplicate inline. -->

# Multi-Agent Mode — Validation Criteria & Anti-Patterns

## Validation criteria (promotion gates from project-local prototype)

| # | Criterion | Measurement | Pass |
|---|-----------|-------------|------|
| 1 | PM never reads worker diffs or worktree files; only the ≤10-line worker summary + `score-state.json` | PM transcript contains zero Read/cat of worktree paths or `gh pr diff` | 0 such reads |
| 2 | No Codex SPOF | inject 1 Codex hang, observe Claude takeover within same round | round closes without user escalation |
| 3 | No orphan branches or worktrees | `git branch --list 'quality/*'` ∖ merged-PR-set, no leftover `.worktrees/quality-*` Codex dirs, Claude Agent worktrees released by harness, and `.worktrees/` gitignored after loop exit | ∅ branches, ∅ worktrees, gitignored |
| 4 | No merge conflicts | parallel-worker merges into main | 0 conflicts |
| 5 | Round count ≤ baseline | multi-agent vs codebase-parallel rounds for same contracts | ≤ |

Criterion #2 ABSTAIN policy: if no Codex worker dispatched OR Codex naturally completed without hang during the run, mark ABSTAIN (not PASS) and inject a synthetic hang in a follow-up validation run. Real-run #1 (2026-05-22) ABSTAINed on #2 — Codex worker completed in 572s on ≤2000-char prompt; counter-evidence to `feedback_codex_cli_hang_pattern` (project-scoped memory; if absent, the inline rule applies: 1st hang on a contract → Claude takeover) memory's 14-17min hang claim for that prompt size class.

## Anti-patterns (multi-agent mode)

- `board.json` schema — filesystem encodes state already; sync burden > value
- Incentive scoring tables — LLMs do not optimize stored priorities; cargo cult
- Reviewer pool separate from worker pool — reviewers = general-purpose Agents drawn on demand
- PM reading full diffs — defeats token preservation
- Parallel dispatch without conflict-group scan — silent contract collision
- Dispatching <3 contracts in parallel — orchestration overhead > savings; fall back to codebase-mode `execution=parallel`
- Sleep-loop timers — use fallback deadline wakeup + `git log` evidence + wall-clock comparison
- PM takeover on worker stuck — escalate to user instead (PM may share contract's blind spot)
- "Skip APPROVE gate" — human-in-the-loop is the calibration mechanism.

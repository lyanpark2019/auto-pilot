---
name: swarm-bench
description: Run a benchmark — same task executed three ways (full swarm, claude opus alone, codex alone), each scored by quality-eval. Output a comparison report. Use when the user says "swarm bench", "/swarm-bench", "compare swarm", "is swarm better than codex", "benchmark autopilot".
argument-hint: "<task description> [--repeats N]"
allowed-tools: Bash, Read, Write
---

# swarm-bench — head-to-head comparison

Empirically measure: does the swarm beat solo `claude opus` or solo `codex`?

## Inputs

- `$ARGUMENTS` = task description (everything before `--repeats`)
- `--repeats N` (default 1): run each arm N times for variance

## Steps

1. Detect swarm. Solo arms (B, C) run regardless. Arm A skipped with a logged
   warning if `tmux has-session -t autopilot-$(basename $PWD)` returns non-zero.
2. Create benchmark dir: `<cwd>/.planning/autopilot/bench/<epoch>/`.
3. Run `bash "${CLAUDE_PLUGIN_ROOT}/scripts/bench.sh" "<task>" --repeats $N`.
   `bench.sh`:
   - **Arm A (swarm)**: inject ticket + wait for PM verdict (poll scores/).
   - **Arm B (claude solo)**: in fresh worktree, `claude -p --dangerously-skip-permissions "<task>"`.
   - **Arm C (codex solo)**: in fresh worktree, `codex exec --full-auto --skip-git-repo-check "<task>"`.
   - For each arm: capture diff, run `quality-eval` skill, record total + per-dimension scores + wall-clock + token usage (from logs).
4. Write `<bench-dir>/report.md` with table:

   | Arm | Score | Time | Tokens | Notes |
   |---|---|---|---|---|
   | swarm | 41/50 | 6m12s | 142k | … |
   | claude-solo | 33/50 | 1m48s | 31k | … |
   | codex-solo | 29/50 | 1m22s | 24k | … |

5. Append narrative: which dimensions did swarm win/lose, cost-per-quality
   ratio, recommendation.

## Notes for Claude

- A baseline ticket should fit one bench run (≤30 min total per arm).
- Wrap solo arms with `timeout 10m` to bound runaway agents.
- `quality-eval` is invoked per arm — same scoring as PM rubric, so arms compare directly.
- Save raw artifacts (diff.patch, log) per arm under `arm-{a,b,c}/`.
- `--repeats N` aggregation: report **median** total per arm and note
  stddev when N ≥ 3. With N=1 (default), report single values.
- Both solo arms use throwaway worktrees (`<basename>-bench-<arm>-<ts>`) so the
  user's main repo is never touched. `--dangerously-skip-permissions` is scoped
  to those throwaway worktrees only.

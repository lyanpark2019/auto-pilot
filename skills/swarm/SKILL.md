---
name: swarm
description: "Auto-pilot multi-agent swarm — subcommand-routed skill: init (config wizard), start (launch tmux PM+workers), status (live diagnostics + ledger), stop (graceful shutdown, --purge worktrees), ticket (manual inbox injection), bench (3-arm head-to-head benchmark: swarm vs claude-opus-solo vs codex-solo, each scored by quality-eval). Use when the user says \"start the swarm\", \"launch swarm\", \"/swarm\", \"start autopilot\", \"deploy multi-agent system\", \"configure swarm\", \"swarm init\", \"set up autopilot\", \"choose workers\", \"swarm status\", \"how is autopilot doing\", \"show swarm\", \"ledger\", \"stop swarm\", \"kill autopilot\", \"shutdown autopilot\", \"tear down swarm\", \"give swarm a task\", \"inject ticket\", \"TODO into swarm\", \"swarm bench\", \"/swarm-bench\", \"compare swarm\", \"is swarm better than codex\", \"benchmark autopilot\", or legacy \"run autopilot-swarm\" / \"/autopilot-swarm\" / \"/swarm-init\" / \"/swarm-status\" / \"/swarm-stop\" / \"/swarm-ticket\"."
argument-hint: "<init|start|status|stop|ticket|bench> [subcommand args]"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# swarm — subcommand-routed multi-agent control

This skill manages the autonomous multi-agent swarm in the **current working
directory**. Six subcommands in one skill:

| `$1` | What it does | Old skill |
|---|---|---|
| `init` | Configuration wizard — creates `config.json` | swarm-init |
| `start` *(or blank)* | Launch tmux session (PM + workers) | swarm (launch) |
| `status` | Live diagnostics, queues, ledger | swarm-status |
| `stop` | Graceful shutdown, optional `--purge` | swarm-stop |
| `ticket` | Manual inbox injection | swarm-ticket |
| `bench` | 3-arm head-to-head benchmark (swarm vs claude-solo vs codex-solo) | swarm-bench (absorbed 2026-06-07) |

**Default when no subcommand given = `start`**, preserving every legacy `/swarm` invocation.

---

## § init — configuration wizard

Build `.planning/autopilot/config.json` from natural-language input or
interactive Q&A. Output drives `start.sh`.

### Inputs

- Optional NL prompt after `init` keyword (i.e. `$ARGUMENTS` minus `"init"`). Examples:
  > "워커 6개. 2개 codex로 codegen, 1개 opus로 architecture review, 3개 sonnet으로 일반. 목표는 이 프로젝트 보안 취약점 제거"
  > "5 workers, mostly haiku, one opus, focus on test coverage"
- If no NL args, fall back to AskUserQuestion (worker count, then per-worker model/role, then goal).

### Output schema (write `<cwd>/.planning/autopilot/config.json`)

```json
{
  "session_name": "autopilot-<basename>",
  "pm": {
    "model": "claude-opus-4-7"
  },
  "workers": [
    {"id": 1, "engine": "claude", "model": "claude-opus-4-7",  "role": "architecture-review"},
    {"id": 2, "engine": "claude", "model": "claude-sonnet-4-6","role": "general"},
    {"id": 3, "engine": "claude", "model": "claude-sonnet-4-6","role": "general"},
    {"id": 4, "engine": "claude", "model": "claude-haiku-4-5", "role": "general"},
    {"id": 5, "engine": "codex",  "model": "gpt-5.5",          "role": "codegen"},
    {"id": 6, "engine": "codex",  "model": "gpt-5.5",          "role": "codegen"}
  ],
  "initial_goal": {
    "title": "이 프로젝트 보안 취약점 제거",
    "themes": ["security", "input-validation", "secrets-handling"],
    "success_criteria": [
      "no high-severity findings from semgrep / bandit",
      "all secrets moved to env",
      "added negative tests for all auth paths"
    ]
  },
  "data_sources": {
    "obsidian": true,
    "notebooklm": true,
    "context7": true,
    "web_search": ["tavily", "brave", "youtube", "reddit"]
  },
  "policy": {
    "max_in_flight_tickets": 10,
    "verifier_enabled": true,
    "self_improve_target": null
  }
}
```

### Constraints

- **PM model is forced to `claude-opus-4-7`** — never let the user override it.
- Worker count must be in `[4, 10]`.
- Per worker, `engine ∈ {claude, codex}`, `model` must match engine
  (claude-* for claude, gpt-5.5 for codex). `role` must match `^[a-z0-9][a-z0-9-]*$`.
- `initial_goal.title` ≤ 80 chars, `success_criteria` ≥ 1 verifiable shell command.
- Refuse and tell user to fix when:
  - `git rev-parse --is-inside-work-tree` fails → `git init`
  - `git rev-parse --verify HEAD` fails → at least one commit required
  - `git config user.email` / `user.name` empty → set them
- Worker IDs must be unique integers, assigned in prompt order starting at 1.

### Normalization rules (NL parser)

Apply BEFORE schema check. Always normalize aliases:

| User says | Canonical |
|---|---|
| `opus`, `claude-opus`, `o4` | `claude-opus-4-7` |
| `sonnet`, `claude-sonnet` | `claude-sonnet-4-6` |
| `haiku`, `claude-haiku` | `claude-haiku-4-5` |
| `codex`, `gpt`, `gpt-5.5` | engine `codex` + model `gpt-5.5` (top tier, default) |
| `gpt-5` (legacy) | engine `codex` + model `gpt-5` |
| `o3` | engine `codex` + model `o3` |
| `arch-review`, `architecture`, `architectural-review` | `architecture-review` |
| `codegen`, `code-generation`, `구현` | `codegen` |
| `general`, `일반` | `general` |
| `security`, `보안` | `security` |
| `verification`, `검증` | `verification` |

### Steps

1. Parse args after `init` (or run AskUserQuestion).
2. Validate against constraints above.
3. Write the json (atomic: temp + rename).
4. Print summary table: pm model, worker list, goal headline.
5. Suggest `/auto-pilot:swarm start` to launch.

### Notes for Claude

- Always echo the parsed config back for user confirmation before writing.
- If user input is ambiguous about engine/model assignment, default to:
  - 1 opus reasoning + 1 codex codegen + (N-2) sonnet general.
- `self_improve_target` non-null = PM will dispatch tickets against that path
  (used for plugin self-improvement).

---

## § start — launch (default subcommand)

Bootstrap the autonomous multi-agent swarm in the **current working directory**.
Universal: works for any language/framework — `swarm-explorer` agent maps the
project at bootstrap.

### Steps

1. **Check for existing config** at `.planning/autopilot/config.json`.
   - If missing, **run the `init` subcommand first** to create one. Do not
     proceed without config.
2. **Verify dependencies** with Bash:
   ```bash
   for cmd in tmux jq envsubst claude codex git; do
     command -v "$cmd" >/dev/null || { echo "missing: $cmd"; exit 1; }
   done
   ```
3. **Run the launcher**:
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/swarm/scripts/start.sh"
   ```
   `start.sh`:
   - Reads `.planning/autopilot/config.json` (worker count, models, initial goal)
   - Creates `<project>/.planning/autopilot/` bus directories
   - Creates N git worktrees at `<project>/../<basename>-worker-{1..N}` on
     branches `autopilot/worker-{1..N}`
   - Starts tmux session `autopilot-<basename>` with 1 PM pane + N worker panes
     (split across 1-2 windows depending on N)
   - Sends pane commands: `bash run-pm.sh` and `bash run-worker.sh <N> <model>`
   - `exec tmux attach` in the **current terminal** (no new window)

### Arguments (passed after `start` or as top-level args when no subcommand)

- `--workers N` — override config worker count (4-10, default from config)
- `--config <path>` — alternate config json (default `.planning/autopilot/config.json`)

### Notes for Claude

- This subcommand must NOT prompt the user mid-launch. Either config exists and we
  go, or we redirect to `init` and stop.
- Resume semantics: if tmux session already exists, just attach.
- Print one final line: `swarm online: <session-name>, <N> workers`.

---

## § status — live diagnostics

Read-only diagnostics for the swarm in the current project.

### Steps

1. Resolve session name: `session=autopilot-$(basename "$PWD")`.
2. `tmux has-session -t "$session"` → if missing, print "swarm not running" and exit.
3. Run, then format the result as a markdown report:
   ```bash
   ROOT=.planning/autopilot
   tmux list-panes -t "$session" -a -F "#{window_index}.#{pane_index} #{pane_current_command}"
   echo "queues:"
   for i in $(jq -r '.workers[].id' "$ROOT/config.json"); do
     echo "  worker-$i inbox=$(ls "$ROOT"/inbox/worker-$i 2>/dev/null | wc -l)"
   done
   echo "in_progress=$(ls "$ROOT"/in_progress 2>/dev/null | wc -l)"
   echo "done=$(ls "$ROOT"/done 2>/dev/null | wc -l)"
   echo "scores=$(ls "$ROOT"/scores/*.json 2>/dev/null | wc -l)"
   echo "ledger:"
   jq '.workers' "$ROOT/ledger/agent-scores.json" 2>/dev/null
   echo "recent scores:"
   ls -t "$ROOT"/scores/*.json 2>/dev/null | head -5 | while read f; do
     jq -c '{id:.ticket_id,worker,total,verdict}' "$f"
   done
   echo "pm log tail:"
   tail -${LOGS:-15} "$ROOT/logs/pm.log" 2>/dev/null
   ```
4. Render as a readable report. Highlight any worker with `weight < 0.7` (struggling) or `weight > 1.3` (top performer).

### Deep diagnostic (F9 — swarm-monitor agent)

If the quick report surfaces ≥ 1 warning (stale in-flight ticket, missing
PM heartbeat, worker with `weight < 0.7`, runaway disk usage, or any
`exit nonzero` line in recent logs), spawn the **swarm-monitor** subagent
via the Task tool for a structured health report. The agent is read-only;
do NOT modify state from this skill.

### Notes for Claude

- Read-only. Do not write. Do not modify the ledger.
- If `--logs N` arg given (after `status`), show last N lines of pm.log.
- Surface in-flight tickets older than 30 minutes as warnings (possibly stuck).

---

## § stop — graceful shutdown

Graceful shutdown of the swarm in the current project.

### Steps

1. `bash "${CLAUDE_PLUGIN_ROOT}/swarm/scripts/stop.sh" $ARGUMENTS`

`stop.sh` behaviour:
- Resolves `session=autopilot-$(basename "$PWD")`.
- If `tmux has-session`, sends `C-c` to all panes (graceful), waits 3s, then `tmux kill-session`.
- If `--purge`, runs `git worktree remove --force` on each worker tree and deletes the `autopilot/worker-N` branches.
- Never touches `main` or non-autopilot branches.
- Leaves `.planning/autopilot/` intact (logs/scores preserved unless user manually rm).

Print: `swarm stopped: <session>` (and `worktrees purged` if `--purge`).

### Notes for Claude

- Always confirm `--purge` with the user once before passing it through.
  (Worktrees may contain uncommitted work.)

---

## § ticket — manual inbox injection

Bypass PM dispatch and put a ticket directly into `worker-N` inbox.

### Parse

Args after `ticket` keyword:
`<worker-id> <task...> [--scope p1] [--scope p2] [--accept c1] [--accept c2]`

- `worker-id` ∈ `1..N` per `config.json`
- `task` is everything else up to first `--scope` / `--accept`
- repeat `--scope` / `--accept` for multiple

If user omits `--scope`, default to `["."]` (full repo, lower priority for PM dispatch overlap).
If user omits `--accept`, derive 1 sane check from project type via `swarm-explorer` snapshot
(`.planning/autopilot/knowledge/project-snapshot.md`).

### Output

Write `<cwd>/.planning/autopilot/inbox/worker-<id>/T-manual-<epoch>.json`:

```json
{
  "id": "T-manual-<epoch>",
  "title": "<<task summary>>",
  "prompt": "<<full task as user typed it, plus scope reminder>>",
  "scope_paths": ["..."],
  "acceptance": ["..."],
  "issued_at": "<iso8601>",
  "issued_by": "user",
  "worktree": "../<basename>-worker-<id>"
}
```

### Steps

1. Validate `worker-id` exists in `config.json`.
2. Verify swarm is running (`tmux has-session`). If not, suggest `/auto-pilot:swarm start`.
3. Write atomically. Print confirmation: `injected T-manual-<epoch> → worker-<id> (will claim within 8s)`.

### Notes for Claude

- Do NOT run the task directly — only deposit the ticket.
- One invocation = one ticket.

---

## § bench — head-to-head comparison

> Provenance: absorbed `swarm-bench` 2026-06-07. Full methodology, no forwarding stub.

Empirically measure: does the swarm beat solo `claude opus` or solo `codex`?
Same task executed three ways, each scored by `quality-eval`, then a comparison
report. The runtime is independent of the swarm lifecycle — solo arms run even
when no swarm is up.

### Inputs

- `$ARGUMENTS` after `bench` keyword = task description (everything before flags).
- `--repeats N` (default 1): run each arm N times for variance.
- `--swarm-timeout SEC` (default 1200): cap how long arm A waits for the PM verdict.
- `--auto-start`: if no swarm session is up, launch one detached (`start.sh
  --no-attach`) for arm A, then stop it (`stop.sh`) after arm A completes.
  A swarm that was already running is never stopped by bench.

### Steps

1. **Detect swarm.** Solo arms (B, C) run regardless. Arm A is skipped with a
   logged warning if `tmux has-session -t "autopilot-$(basename "$PWD")"` returns
   non-zero (`bench.sh` writes `arm-a/skipped` and still runs B/C) — unless
   `--auto-start` is given, in which case bench launches the swarm detached,
   runs arm A, and stops the self-started swarm before arms B/C.
   ⚠️ A live swarm pushes worker branches / opens PRs when `gh` + an `origin`
   remote exist (`run-worker.sh` auto-PR) and the PM cherry-picks merge-verdict
   commits into the default branch (`pm-ledger.md`). For a side-effect-free
   bench, run in a scratch clone without `origin`.
2. **Benchmark dir** is created by the script at
   `<cwd>/.planning/autopilot/bench/<epoch>/` with `arm-a/`, `arm-b/`, `arm-c/`.
3. **Run the harness**:
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/swarm/scripts/bench.sh" "<task>" --repeats $N
   ```
   `bench.sh`:
   - **Arm A (swarm)**: injects a manual `T-bench-<ts>-rN.json` ticket into the
     first worker's inbox, then polls `scores/T-bench-<ts>-rN.json` until the PM
     records a verdict (or `--swarm-timeout` elapses, or a `STOP` file appears).
     Copies the score json + `results/` artifacts into `arm-a/`.
   - **Arm B (claude opus solo)**: in a throwaway worktree on branch
     `bench/b/<ts>/rN`, runs
     `timeout 600 claude --model claude-opus-4-7 -p --dangerously-skip-permissions "<task>"`.
   - **Arm C (codex solo)**: in a throwaway worktree on branch `bench/c/<ts>/rN`,
     runs `timeout 600 codex exec --model gpt-5.5 -c model_reasoning_effort="xhigh" --sandbox workspace-write --skip-git-repo-check "<task>"`.
   - For each solo arm: commits the result (`--allow-empty`), captures
     `diff-rN.patch` (vs `HEAD~1`, or empty-tree on first commit), records
     `wall_seconds_all`.
   - **Scores arms B/C** by spawning `claude --model claude-opus-4-7 -p` to run
     `Skill(quality-eval)` on the last-rep worktree, capturing
     `arm-{b,c}/quality-eval.md` (same rubric as the PM, so arms compare directly).
   - **Aggregates** per-arm median wall time (`median()` helper — numeric sort,
     lower-middle for even N), writes `arm-*/wall_seconds`, then emits
     `<bench-dir>/report.md`.
4. The generated `report.md` table:

   | Arm | Median Wall (s) | Notes |
   |---|---|---|
   | A swarm | <median> | swarm score `.total` from `arm-a/score.json` |
   | B claude-opus-solo | <median> | see `arm-b/quality-eval.md` |
   | C codex-gpt5-solo | <median> | see `arm-c/quality-eval.md` |

5. After `bench.sh` returns, read the artifacts and **append a narrative** to
   `report.md`: which dimensions the swarm won/lost, cost-per-quality ratio,
   and a recommendation.

### Notes for Claude

- A baseline ticket should fit one bench run (≤30 min total per arm).
- Solo arms are wrapped in `timeout 600` (10m) to bound runaway agents; arm A is
  bounded by `--swarm-timeout`.
- `quality-eval` is invoked per arm — same scoring as the PM rubric, so arms are
  directly comparable. Report total + per-dimension scores + wall-clock; pull
  token usage from logs when available.
- Save raw artifacts (`diff-rN.patch`, `log-rN.md`, `score*.json`, `result-rN/`)
  per arm under `arm-{a,b,c}/`.
- `--repeats N` aggregation: report **median** wall time per arm and note stddev
  when N ≥ 3. With N=1 (default), report single values.
- Both solo arms use throwaway worktrees (`../<basename>-bench-<arm>-<ts>-rN`) so
  the user's main repo is never touched. `--dangerously-skip-permissions` is
  scoped to those throwaway worktrees only.

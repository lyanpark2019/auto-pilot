---
name: swarm-init
description: Interactively configure the autopilot swarm for the current project — natural-language wizard that picks worker count, per-worker model + role, and the initial high-level goal. Writes .planning/autopilot/config.json. Use when the user says "configure swarm", "swarm init", "/swarm-init", "set up autopilot", "choose workers", or before first launch.
argument-hint: "[<natural-language config>]"
allowed-tools: Bash, Read, Write, AskUserQuestion
---

# swarm-init — configuration wizard

Build `.planning/autopilot/config.json` from natural-language input or
interactive Q&A. Output drives `start.sh`.

## Inputs

- Optional NL prompt as `$ARGUMENTS`. Examples:
  > "워커 6개. 2개 codex로 codegen, 1개 opus로 architecture review, 3개 sonnet으로 일반. 목표는 이 프로젝트 보안 취약점 제거"
  > "5 workers, mostly haiku, one opus, focus on test coverage"
- If no `$ARGUMENTS`, fall back to AskUserQuestion (worker count, then per-worker model/role, then goal).

## Output schema (write `<cwd>/.planning/autopilot/config.json`)

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
    {"id": 5, "engine": "codex",  "model": "gpt-5",            "role": "codegen"},
    {"id": 6, "engine": "codex",  "model": "gpt-5",            "role": "codegen"}
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

## Constraints

- **PM model is forced to `claude-opus-4-7`** — never let the user override it.
- Worker count must be in `[4, 10]`.
- Per worker, `engine ∈ {claude, codex}`, `model` must match engine
  (claude-* for claude, gpt-5 for codex), `role` is free-form lowercase tag.
- `initial_goal.title` ≤ 80 chars, `success_criteria` ≥ 1 verifiable item.
- If the project has no `.git`, refuse and tell user to `git init` first
  (worktrees require a repo).

## Steps

1. Parse `$ARGUMENTS` (or run AskUserQuestion).
2. Validate against constraints above.
3. Write the json (atomic: temp + rename).
4. Print summary table: pm model, worker list, goal headline.
5. Suggest `/autopilot-swarm:autopilot-swarm` to launch.

## Notes for Claude

- Always echo the parsed config back for user confirmation before writing.
- If user input is ambiguous about engine/model assignment, default to:
  - 1 opus reasoning + 1 codex codegen + (N-2) sonnet general.
- `self_improve_target` non-null = PM will dispatch tickets against that path
  (used for plugin self-improvement).

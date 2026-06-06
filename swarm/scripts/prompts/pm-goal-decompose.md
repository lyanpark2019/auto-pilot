You are the PM (claude-opus-4-7) for ${PROJECT}.

## Decompose the initial goal into an executable roadmap

Read `.planning/autopilot/config.json` → `initial_goal`, plus
`knowledge/project-snapshot.md` and `knowledge/synthesis.md`.

## Output (write `${PROJECT}/.planning/autopilot/knowledge/roadmap.json`)

```json
{
  "goal_title": "<copy from config>",
  "milestones": [
    {
      "name": "M1: secrets audit",
      "success_criteria": ["grep -r 'sk-' src/ returns 0", "all secrets via env"],
      "estimated_tickets": 3,
      "depends_on": []
    },
    {"name":"M2: input validation","success_criteria":[...],"estimated_tickets":5,"depends_on":["M1"]},
    ...
  ],
  "exit_criteria": [
    "all milestone success_criteria pass",
    "no high-severity findings from <tool>",
    "test suite green"
  ]
}
```

## Rules

- 3-7 milestones. Each must be runnable as 2-5 worker tickets.
- Every success_criterion must be VERIFIABLE by a shell command (Bash one-liner).
- Include `exit_criteria` so the PM knows when to stop dispatching goal-related
  tickets and switch to maintenance.
- Stdout: `roadmap: <N> milestones, <T> tickets estimated`.

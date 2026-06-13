You are an INDEPENDENT VERIFIER (independent verifier) for ${PROJECT}. Second opinion on **${SCORE_TID}**.

Authoritative rubric: see swarm/scripts/prompts/_RUBRIC.md in the auto-pilot plugin (must match scorer dim names + hard rules + verdict bands).

## Delegation (F9 — agents/swarm-verifier.md is the implementation)

Spawn the **swarm-verifier** subagent via the Task tool with the inputs below.
Pass `${SCORE_TID}` and the project absolute path. Use the agent's output as
the verification result. If the Task tool is unavailable in the current
session (e.g. headless `claude -p` without agent registry), fall back to
executing the steps below inline.

You did NOT score this ticket. Read it fresh.

## Inputs

- The score file: `.planning/autopilot/scores/${SCORE_TID}.json`
- All artifacts from the original score's references (ticket, diff, worker log)
- Worktree at the score's worktree path

## Your job

1. **Re-run** every `acceptance` command independently. Don't trust the score's recorded exits.
   Record raw stdout of every acceptance command into evidence.cmd_output (truncate to last 4 KB if huge).
2. **Re-inspect** the diff for:
   - Hidden side-effects (file deletes outside scope_paths, dependency changes, secret leakage)
   - Test gaming (tests that always pass, removed assertions, mocked-away assertions)
   - Comment-only changes claimed as fixes
3. **Adversarial probe**: try to break the change. Suggest 1-3 inputs/scenarios
   the worker did NOT handle. If any can be demonstrated as a real bug via a
   short bash command, the verdict MUST be downgraded.

## Output (rewrite `${PROJECT}/.planning/autopilot/scores/${SCORE_TID}.json` atomically)

Keep all existing fields. Add:

Verifier output MUST validate against swarm/schemas/verify.schema.json (in the auto-pilot plugin).

```json
{
  "verifier": {
    "passed": true,
    "evidence": {
      "cmd_output": "<raw stdout of acceptance commands, last 4 KB>",
      "files_checked": ["path/to/file1", "path/to/file2"],
      "diff_sha": "abc1234"
    },
    "reproductions": [
      {"scenario":"...","cmd":"...","observed":"..."}
    ],
    "downgraded_to": null,
    "notes": "<paragraph>"
  }
}
```

If `verifier.passed == false`, update top-level `verdict` to match `downgraded_to`.

Stdout: `verified ${SCORE_TID}: passed=<bool>`.

## Rubric coherence

Before scoring, self-check: these 5 dimension identifiers must appear in your output JSON rubric field verbatim:
- `correctness`
- `scope_discipline`
- `test_coverage`
- `code_quality`
- `alignment_with_acceptance`

Hard rules: acceptance fail → max `alignment_with_acceptance=3`; empty diff → total 0 verdict reject.
Verdict bands: merge ≥ 40 / request-changes 25-39 / reject ≤ 24.

## Bias controls

- DO NOT read or be influenced by the original scoring notes before forming your own conclusion.
- Treat ≥40 totals with extra skepticism — high scores attract verification.
- A clean `verifier.passed=true` is fine and common — do NOT manufacture issues.

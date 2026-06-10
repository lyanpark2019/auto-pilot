**[HEADLESS MODE — auto-pilot server]**

First action: run `echo "HEADLESS=${HARNESS_HEADLESS:-0}"`.

If `HEADLESS=1` (it will be), this session is a non-interactive auto-pilot worker.
Rules:
- Never call AskUserQuestion. Never wait for confirmation.
- If a skill or subagent says "ask the user", use the most reasonable default and proceed.
- stdin is /dev/null — there is no one to answer.
- Stop conditions are state.json driven, not user driven.
- ALL subagent dispatch (workers AND reviewers) is SYNCHRONOUS: foreground Bash
  or blocking wait (`_reviewer_wrapper.wait_all`). NEVER any background/async
  launch — `run_in_background`, trailing `&`, `nohup`, detached wrappers, or any
  equivalent. NEVER exit with subagents in flight — when this one-shot session
  ends, nothing wakes up to collect them; the loop burns iterations re-validating
  the same phase until an orphan happens to finish (live failure 2026-06-10, F-6).

---


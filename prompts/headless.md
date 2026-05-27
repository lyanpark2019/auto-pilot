**[HEADLESS MODE — auto-pilot server]**

First action: run `echo "HEADLESS=${HARNESS_HEADLESS:-0}"`.

If `HEADLESS=1` (it will be), this session is a non-interactive auto-pilot worker.
Rules:
- Never call AskUserQuestion. Never wait for confirmation.
- If a skill or subagent says "ask the user", use the most reasonable default and proceed.
- stdin is /dev/null — there is no one to answer.
- Stop conditions are state.json driven, not user driven.

---


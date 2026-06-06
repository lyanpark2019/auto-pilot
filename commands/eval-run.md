---
name: eval-run
description: Run the cut-1 evals harness (advisory). Clones the repo per case, runs auto-pilot headless on the case spec, asserts the deliverable with a deterministic oracle, prints an advisory pass-rate vs the blessed baseline. Never blocks (cut-1). Usage `/auto-pilot eval run [--tier smoke|full] [--case ID] [--repeats N]`.
allowed-tools: Bash(python3 ${CLAUDE_PLUGIN_ROOT}/scripts/evals/cli.py:*)
---

Run the evals harness in advisory mode:

!`python3 ${CLAUDE_PLUGIN_ROOT}/scripts/evals/cli.py run --tier smoke --repeats 1`

You are resuming the auto-pilot loop. Iteration {iter_n}, phase {phase}.

Run the `auto-pilot` skill: read state.json, plan contracts, dispatch workers + dual reviewers,
verify, commit with trailers `auto-pilot-iter: {iter_n}` and `auto-pilot-phase: {phase}`,
advance phase. STOP this session after one phase completes (do not loop in-session — the
outer headless-loop.py drives the next iteration).

Dispatch discipline: workers AND reviewers run synchronously — wait for their
done.marker/review.json IN THIS SESSION before exiting. Ending the session with
subagents in flight strands them (no wake-up exists in headless mode).

On any unrecoverable error, update state.json status to 'failed' before exiting.
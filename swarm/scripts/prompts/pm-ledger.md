You are the PM (orchestrator PM) for ${PROJECT}. Reconcile scores → ledger → merge winners.

## Inputs

- New score files: `${PROJECT}/.planning/autopilot/scores/*.json` not in `ledger.processed[]`
- Ledger: `${PROJECT}/.planning/autopilot/ledger/agent-scores.json`
- Worker branches `autopilot/worker-N`

## Steps

1. For each unprocessed score:
   - Update `ledger.workers[<worker>]`:
     - `tickets += 1`, `sum_score += total`, `avg = sum_score/tickets`
     - `streak`: +1 if `total >= policy.incentive_threshold` else 0
     - `weight`:
       - merge → `min(weight + step, max)`
       - reject → `max(weight - step, min)`
       - request-changes → unchanged
     - `last_total`, `last_verdict`, `last_model`
   - Append `ticket_id` to `ledger.processed` (cap at last 500).
2. **Merge policy**: for `verdict == "merge"` AND (verifier present → `verifier.passed == true`),
   cherry-pick the worker's commit into the project's default branch
   (HEAD branch, usually `main`):
   ```
   cd ${PROJECT}
   DEFAULT="$(git symbolic-ref --short HEAD)"
   git cherry-pick <sha> || git cherry-pick --abort
   ```
   On conflict: abort, rewrite the score with `verdict: request-changes` + note `cherry-pick-conflict`.
3. **Graph refresh** — after each successful cherry-pick, if `${PROJECT}/graphify-out/`
   exists, run `graphify update "${PROJECT}"` (AST-only, no API cost). Best-effort:
   on failure, log `graphify-update-failed: <code>` and continue. The next bootstrap
   reads the refreshed graph automatically.
4. Write ledger atomically (write to `.tmp`, then rename).

## Output

- Updated ledger.json
- Stdout: `ledger: processed <n>, merged <m>, conflicts <c>, rejects <r>`.

## Rules

- Never modify worker branches.
- Never `git push` — local only. User decides when to push.
- If processed[] missing, initialize as `[]`.

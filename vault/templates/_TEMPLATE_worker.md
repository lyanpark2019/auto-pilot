---
name: template-worker
description: Use this agent when [conditions]. Typical triggers include [scenario 1], [scenario 2], and [scenario 3]. See "When to invoke" in the agent body for worked scenarios.
tools: Bash, Read, Write, Edit, Grep, Glob
model: sonnet
color: blue
---

# {{Worker Name}}

> **Template — copy this file and rename. Drop the `_TEMPLATE_` prefix.**
> selftest.py auto-excludes files prefixed `_`.

## Mission

One paragraph. What dim of the rubric this worker improves. What honest signal it changes (graph.json edges? wiki page bodies? .graphify_labels.json?).

## Inputs

- `<vault>/meta/score-state.json` — read current score for target dim
- `<vault>/<cat>/raw/graphify-out/graph.json` — graph store (most workers)
- Ticket context — `t.contract` fields: `goal`, `inputs`, `outputs`, `acceptance`, `reward`
- Additional inputs specific to this worker

## Workflow

1. Read ticket context (PM injects via `t.to_prompt_context()`)
2. Parse current state for target dim — what's the gap?
3. For each category (or scoped subset):
   - Compute current sub-metric
   - Apply deterministic, evidence-based fix
   - Log to `<vault>/meta/<worker>-actions.md`
4. After all edits, write deliverable summary
5. Re-score the target dim to confirm improvement (optional — PM verifies)

## Idempotency + backup

If destructive edits, use `WorkerBackup` from `scripts/worker_backup.py`:

```python
from worker_backup import WorkerBackup
bak = WorkerBackup(vault, worker="my-worker", round_num=N, ticket_id=t.id)
bak.snapshot(file_to_modify)
# ... mutate ...
bak.commit()   # success — PM may purge later
# OR
bak.rollback()  # if mid-flight error
```

PM can rollback via `WorkerBackup.rollback_ticket(vault, ticket_id)` on verifier reject.

## Cost telemetry

If running as Agent subagent, the dispatcher captures `usage` from Agent reply. PM passes to:

```python
from cost_tracker import CostTracker
CostTracker(vault).record(round_num, "my-worker", usage_dict, model="sonnet", ticket_id=t.id)
```

## Output (stdout JSON)

```json
{
  "status": "delivered",
  "round": N,
  "ticket_id": "...",
  "cats_touched": ["cat-a", "cat-b"],
  "items_modified": K,
  "target_dim_before": X,
  "target_dim_after": Y,
  "deliverable_paths": ["<vault>/meta/<worker>-actions.md"]
}
```

## Task boundaries

- ❌ Don't fabricate data — every change must trace to filesystem evidence (raw md, existing graph node, etc)
- ❌ Don't touch files outside ticket scope
- ❌ Don't loop forever — exit after delivering JSON
- ❌ Don't modify EXTRACTED edges (they're grounded — corruption invalidates audit trail)
- ❌ Don't push AMB band past 15% per cat (rubric confidence_balance dim)
- ✅ Always log changes for auditor verification
- ✅ Deterministic: same input → same output (use `random.Random(seed)` if sampling)
- ✅ Update `verification_status` / `last_modified` frontmatter where applicable
- ✅ Skip silently if input file missing (return status "no-input")

## Stop criteria

Worker exits after:
1. Target dim measurably improved, OR
2. Acceptance threshold met per ticket contract, OR
3. No actionable items found (return status "no-op")

## Anti-patterns to avoid

- "Run forever to maximize score" — exit after single pass
- "Self-verify and claim success" — leave verification to PM/auditor
- "Touch unrelated dims" — stay scoped to target_dimension
- "Invent citations" — only cite what actually exists in raw text

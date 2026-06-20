# Archon-side PoC files (canonical copy)

These are the Archon-engine-side files for the learning-loop→Archon PoC. The
canonical, version-controlled copy lives here; the live run deploys them into
the local Archon clone's `.archon/scripts/` directory.

Deploy: copy `run_id_from_diff.sh` and `archon_review_to_jsonl.py` into the
Archon repo's `.archon/scripts/` folder before running the workflow.

- `run_id_from_diff.sh` — stable diff-identity RUN_ID (git rev-parse HEAD on a
  clean tree, shasum(diff.patch) fallback; never the per-run Archon workflow id).
- `archon_review_to_jsonl.py` — review.json → critic-rejections-phase-0.jsonl
  adapter (REJECT + P0/P1 only, title→issue, class from the frozen
  REVIEWER_FINDING_CLASSES vocab, dedupe on canonical line key).
- `test_*` — standalone self-tests. Run directly:
  `bash test_run_id_from_diff.sh` and `python3 test_archon_review_to_jsonl.py`.

Known integration hazards to honor when wiring the YAML (Task 9):
- run_id reflects the reviewed unit: ensure each stage-A diff is a DISTINCT
  commit, or leave the tree dirty so the shasum(diff.patch) fallback fires —
  otherwise two different diffs against the same clean HEAD collide and
  distinct_runs never reaches 2.
- The adapter must receive a non-empty RUN_ID in its environment, else the
  miner collapses all findings into one legacy run id.

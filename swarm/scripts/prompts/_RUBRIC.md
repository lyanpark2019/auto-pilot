# Autopilot Swarm — Canonical Rubric

Single source of truth. pm-score.md, pm-verify.md, and agents/swarm-verifier.md
all reference this file. Any rubric change MUST be made here first.

## Dimensions

Each dimension scored 0-10. Sum 0-50.

- `correctness`
- `scope_discipline`
- `test_coverage`
- `code_quality`
- `alignment_with_acceptance`

Descriptions:
- **correctness** — does the diff implement the ticket title?
- **scope_discipline** — only files inside ticket `scope_paths`?
- **test_coverage** — tests added or updated?
- **code_quality** — quality-eval dims; no magic numbers; types present; files ≤ 500 LoC
- **alignment_with_acceptance** — ALL acceptance commands exited 0?

## Hard rules

- acceptance fail → max `alignment_with_acceptance=3`
- empty diff → total 0 verdict reject

## Verdict bands

- merge ≥ 40
- request-changes 25-39
- reject ≤ 24

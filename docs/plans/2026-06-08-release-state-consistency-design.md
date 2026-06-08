---
topic: release-state-consistency
date: 2026-06-08
---

# Release State Consistency Design

## Goal

Keep the persisted quality score state consistent with shipped plugin releases so
future agents do not treat an already-published release as blocked or pending.

## Current mismatch

`v0.8.7` is tagged and released from commit `e3200cb`, both plugin manifests are
`0.8.7`, and hosted CI run `27138414829` passed. The quality state file still
records `CI_FIX_PUSH_READY`, pending hosted CI/release residual risks, and a
blocked decision.

## Approach

Add a repository test that validates release-state invariants from tracked files:
when the plugin manifest version is `0.8.7`, `.planning/quality/score-state.json`
must report a released state, include the release tag, release URL, CI run, and
release commit, and must not keep pending/blocker language in residual risks or
decision text.

Then update only the quality state evidence to match the shipped release. This is
lower risk than changing runtime code and directly protects the audit trail.

## Testing

- RED: add the release-state invariant test and run it against the current stale
  state; it must fail on `current_state`/pending evidence.
- GREEN: update `.planning/quality/score-state.json` with release evidence.
- Verification: run the targeted test, quality metric snapshot smoke if touched,
  root pytest, ruff, and mypy.

## Non-goals

- Do not move `v0.8.7` or older tags.
- Do not change plugin runtime behavior.
- Do not broaden scoring dimensions or start a new adversarial rescore.

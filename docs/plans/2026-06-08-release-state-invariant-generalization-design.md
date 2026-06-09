---
topic: release-state-invariant-generalization
date: 2026-06-08
---

# Release State Invariant Generalization Design

## Goal

Reduce release-train maintenance in `tests/test_release_state.py` without
weakening the `v0.8.7` audit evidence.

## Current shape

The release-state test locks `EXPECTED_VERSION`, `EXPECTED_STATE`, tag, commit,
CI run, and release URL as top-level constants. This catches stale state for the
current release, but it duplicates values derivable from plugin manifests and
makes the next release update more error-prone than needed.

## Approach

Keep immutable release evidence checks for the shipped release commit, hosted CI
run, and GitHub release URL. Derive consistency checks from the plugin manifests:

- manifest version must match marketplace version,
- release tag must be `v{manifest_version}`,
- release `plugin_version` and `marketplace_version` must match the manifests,
- `current_state` must be the normalized released state for the manifest version.

This keeps the evidence strict while making the invariant reusable for the next
release train.

## Testing

Use a RED test that mutates in-memory fixture copies of the loaded manifest/state
data from `0.8.7` to a hypothetical `0.8.8`. The current hardcoded test helper
cannot validate that scenario. Then refactor the test around a small assertion
helper and verify both current `v0.8.7` evidence and the synthetic `v0.8.8`
consistency case.

## Non-goals

- Do not change `.planning/quality/score-state.json` release evidence.
- Do not move tags or create a new release.
- Do not change runtime code.

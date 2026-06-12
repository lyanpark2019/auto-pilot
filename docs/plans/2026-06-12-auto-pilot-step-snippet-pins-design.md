# auto-pilot Step Snippet Pins Design

## Scope

This PR pins the two fenced pre-flight snippets in `skills/auto-pilot/SKILL.md`:

- Step 7 — hardened reviewer registry presence check.
- Step 8 — Codex sandbox capability probe.

It does not change runtime behavior or hook logic.

## Approach

Add a small Bats suite under `skills/auto-pilot/tests/` that reads `../SKILL.md` and asserts the load-bearing lines still exist inside the relevant fenced snippets. Wire that suite into CI and the repo verification docs so the markdown cannot silently regress.

## Alternatives considered

1. **Dedicated auto-pilot Bats suite** — recommended. Local to the skill and explicit in CI.
2. **Piggyback on ARL Bats** — smaller CI diff, but tests the wrong skill directory and obscures ownership.
3. **Python markdown parser** — stronger structure checks, but unnecessary for two fenced snippets.

## Test design

Use narrow substring pins rather than full snapshots. The Step 7 test should assert the registry check still:

- requires `CLAUDE_PLUGIN_ROOT`,
- checks both hardened reviewer names,
- reads `${CLAUDE_PLUGIN_ROOT}/agents/${agent}.md`,
- anchors the `name:` match to frontmatter with `sed -n '2,/^---$/p'`,
- exits with status 3 on missing reviewers.

The Step 8 test should assert the sandbox probe still:

- uses `codex exec --help`, not a live `codex exec` probe,
- greps for `--sandbox`,
- exports `AUTO_PILOT_CODEX_SANDBOX_AVAILABLE=1` on support,
- exports `AUTO_PILOT_CODEX_SANDBOX_AVAILABLE=0` otherwise.

Run:

```bash
cd skills/auto-pilot && bats tests/
```

## Out of scope

- URL-shaped `TICKET=` false positives.
- `verifier_agents` reuse-name alignment.
- `contract_dir=` prose-trip hardening, which remains a documented residual because narrowing that marker can weaken real dispatch gating.

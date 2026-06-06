You are the PM (claude-opus-4-7). SPECIAL TICKET: improve the auto-pilot
plugin's swarm subsystem itself.

## Target

`config.policy.self_improve_target` (a path, e.g. `${HOME}/.claude/plugins/auto-pilot`).

Workers will operate on a worktree of THAT repo, not the current project.

## Steps

1. Read `${PROJECT}/.planning/autopilot/config.json` and confirm
   `policy.self_improve_target` is a non-empty path that exists.
2. Read the plugin's existing files for context:
   - `<target>/README.md`
   - `<target>/skills/*/SKILL.md`
   - `<target>/swarm/scripts/*.sh`
   - `<target>/swarm/scripts/prompts/*.md`
3. Use `Skill(superpowers:adversarial-review-loop)` mental model to find issues:
   - logic bugs in bash scripts
   - prompt ambiguities that could produce bad json
   - missing edge-case handling (e.g., worktree path collisions, json parse errors)
   - benchmarking gaps
4. Pick ONE concrete improvement (smallest viable). Emit a normal ticket
   pointing at `<target>` as the worktree, with `topic="self-improve"`.

## Output

Same schema as `pm-dispatch`, but:
- `worktree` = `policy.self_improve_target`
- `topic`    = `"self-improve"`
- `scope_paths` confined to ONE subdir of the target
- `acceptance` MUST include: `bash -n <changed shell scripts>` syntax check.

Stdout: `self-improve ticket issued: <id>`.

## Stop condition

If three consecutive self-improve tickets land verdict=merge with score>=45,
PM may pause self-improvement and resume normal goal work.

---
name: codex-orchestra
description: "Conductor mode — Claude plans, reviews, and gates while Codex (gpt-5.5/xhigh, workspace-write) writes implementation code through codex-companion task --write. Use ONLY on explicit /codex-orchestra or the phrase \"codex orchestra\". Runs a Plan -> Implement -> Review -> Commit loop with pause points. Do NOT auto-trigger on generic words like \"orchestrate\" or \"conductor\"."
trigger: /codex-orchestra
---

# /codex-orchestra

Claude is the **conductor**: plan, dispatch Codex work, review the diff, and gate
commits. Claude does **not** write implementation source or test code in this mode.
Modeled on `ShepAlderson/copilot-orchestra`, adapted to the installed
`openai-codex` plugin.

## Runtime Contract

Primary helper:

```bash
CC="$HOME/.claude/plugins/marketplaces/openai-codex/plugins/codex/scripts/codex-companion.mjs"
node "$CC" task --write --model gpt-5.5 --effort xhigh "<handoff prompt>"
```

- `task --write` runs Codex with `sandbox: workspace-write`, not unrestricted
  machine access. It may edit inside the workspace; network, out-of-workspace writes,
  and privileged operations can still gate.
- `task` supports `[--background] [--write] [--resume-last|--resume|--fresh]
  [--model] [--effort] [prompt]`. It does **not** support `--wait`.
- Foreground execution means omit `--background`. For a long phase, launch
  `task --background` from the main thread, then poll with `status` and fetch
  with `result`.
- Do not use direct `codex exec` with sandbox/approval bypass flags for orchestra
  unless the user explicitly changes this plan.

## Role Split

- **Claude MAY**: read files, use Explore subagents for research, write `plans/`
  artifacts, run codex-companion Bash commands, review diffs read-only, and gate.
- **Claude MUST NOT**: write or edit implementation source or test files.
- **Codex writes code/tests** through `codex-companion task --write`.
- On Codex failure, empty output, or malformed output, Claude triages and reports;
  it never self-implements the missing code.

## Phase 0 — Preflight

Run these before each same-repo phase:

1. Confirm Codex is available (`codex --version`). Use `/codex:setup` only for
   availability, authentication, or review-gate setup. It does not set repo trust.
2. Confirm the target repo is trusted in `~/.codex/config.toml`
   (`trust_level = "trusted"` for that project).
3. Check queue state:

```bash
node "$CC" status --all --json
```

If any `task` job is `queued` or `running`, inspect whether it is genuinely live.
Probe the stored `pid` with `kill -0 <pid>` when present. Wait for a live job or
cancel an orphaned/stale job with:

```bash
node "$CC" cancel <jobId>
```

Do not dispatch a same-repo implementation phase while another task job is active.

## Phase 1 — Plan

Research with reads and Explore subagents. Draft a repo-local
`plans/<task>-plan.md` with small phases, affected files, non-goals, and
verification commands.

**Pause for user approval before implementation.**

## Phase 2 — Implement

Fill the handoff template below into a tight, self-contained prompt, then run:

```bash
node "$CC" task --write --model gpt-5.5 --effort xhigh "<handoff prompt>"
```

For long phases only:

```bash
node "$CC" task --background --write --model gpt-5.5 --effort xhigh "<handoff prompt>"
node "$CC" status <jobId> --wait   # --wait is a *status* flag (task does not support it)
node "$CC" result <jobId>
```

`--wait` belongs to review/status execution control, not to `task`. If using the
`codex:codex-rescue` forwarder outside orchestra, treat `--wait` as Claude-side
routing control only; the forwarder strips it before calling `task`.

## Handoff Prompt Template

Codex does not share Claude's context. Every prompt must stand alone:

```xml
<task>This phase's concrete job only.</task>
<context>Relevant file paths, patterns, repo conventions, and approved plan excerpt.</context>
<completeness_contract>Exact acceptance criteria. Run tests/build and report command output.</completeness_contract>
<verification_loop>How Codex should self-check before finishing.</verification_loop>
<action_safety>Stay in scope and in this workspace. No unrelated refactors. Stage nothing. Do not commit.</action_safety>
<structured_output_contract>Return exactly these sections: Summary, Validation, Remaining Risks, Files Changed.</structured_output_contract>
```

The four-section output is prompt-only, not a runtime schema. Claude must verify
that all required sections are present before review:

- `Summary`
- `Validation`
- `Remaining Risks`
- `Files Changed`

If output is empty or missing sections, run main-thread triage:

```bash
node "$CC" status --all --json
node "$CC" result <jobId>
```

Then halt and report the failure.

## Phase 3 — Review

Read the diff read-only. Verdict precedence:

1. Codex's `Validation` reports green test/build output.
2. The diff stays in the approved scope with no obvious correctness or security
   issue.

Return `APPROVED`, `NEEDS_REVISION`, or `FAILED`.

Optional second opinion:

```bash
node "$CC" adversarial-review --scope working-tree
```

After presenting findings, stop and confirm revision scope. For `NEEDS_REVISION`,
dispatch a fresh, fully self-contained Codex prompt. Do not depend on
`--resume-last` for correctness.

## Phase 4 — Commit Gate

Present the summary, files changed, validation evidence, remaining risks, and a
proposed commit message. The user commits if they choose. If asked to commit,
stage explicit paths only; never use `git add -A`.

For multi-phase tasks only, write `plans/<task>-phase-<N>-complete.md` and a final
`plans/<task>-complete.md`. Single-phase tasks skip that ceremony.

## Constraints

- Serial within a repo. Parallel work requires separate independent worktrees or
  directories.
- Background task jobs are launched only from the main thread, never from a Claude
  subagent.
- `--resume-last` is an optimization only. Revision prompts stay self-contained.
- `codex:codex-rescue` is a one-shot `task` forwarder. It cannot review, status,
  result, or cancel for the conductor.

## Per-Project Enforcement (live)

Conductor stance is advisory by default. A repo opts into **hard** enforcement by
dropping a marker at its root:

```bash
touch <repo-root>/.codex-conductor   # enable: block Claude code/test edits
rm    <repo-root>/.codex-conductor   # disable
```

A `PreToolUse(Edit|Write|MultiEdit|NotebookEdit)` hook
(`${CLAUDE_PLUGIN_ROOT}/hooks/codex-conductor-guard.py`, registered in this
plugin's `hooks/hooks.json`) then denies Claude edits to source/test code in that
repo and points back to `/codex-orchestra`. Markdown/docs/text and anything under
`plans/` stay editable so the conductor can still write artifacts. Repos without
the marker are unaffected (hook fails open).

## If the Slash Does Not Fire

`name` + `trigger: /codex-orchestra` should resolve the slash command, matching the
working `graphify` precedent. Add a thin `~/.claude/commands/codex-orchestra.md`
shim only after observing that `/codex-orchestra` does not resolve.

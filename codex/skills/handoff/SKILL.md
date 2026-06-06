---
name: handoff
description: Compact the current conversation into a handoff document for another agent or session. Use when the user asks for a handoff, continuation note, session summary, or next-agent briefing.
---

# Handoff


Use this skill to write a concise handoff document that lets a fresh agent continue the work.

## Codex Coordination

- Obey the active collaboration mode. In Plan Mode, inspect and propose only; do not mutate files, issues, branches, or external systems.
- Read local `AGENTS.md`, `CLAUDE.md`, and nested instructions before repository writes.
- Preserve unrelated dirty work. Never bulk-stage, bypass hooks, or run destructive commands without explicit approval.
- If another active skill gives stricter verification or safety rules, follow the stricter rule.

The handoff is the artifact; do not modify repository files unless the user explicitly asks for a repo-stored handoff.

## Output Contract

Report the temporary handoff path and one highest-priority next action. The document itself should include objective, state, decisions, files/refs, commands run, pending tasks, blockers, risks, skipped checks, and suggested skills.


## Source Fidelity Notes

If the user passed arguments, treat them as the next session focus and tailor the handoff to that purpose.
## Destination

Save the handoff in the operating system temporary directory, not the current workspace.
Use a descriptive filename such as `/private/tmp/codex-handoff-YYYYMMDD-HHMMSS.md` on macOS.

## Include

- Objective and current state.
- Decisions made and assumptions.
- Files, branches, issues, PRs, or plans to read next.
- Commands already run and key outcomes.
- Pending tasks in recommended order.
- Blockers, risks, and skipped verification.
- Suggested skills to invoke next.

## Exclude

- Do not duplicate full PRDs, plans, ADRs, issue bodies, commits, or diffs when a path or URL is enough.
- Redact API keys, tokens, credentials, private key names, raw sensitive logs, and unnecessary personal data.
- Do not store the handoff in the repo unless the user explicitly asks.

## Finish

Report the handoff path and the most important next action.

---
name: llm-wiki-architect
description: Use when a repository needs an LLM wiki, module-boundary map, Obsidian-style knowledge index, Graphify refresh policy, or a pre-edit structure gate that keeps future code changes inside stable module ownership.
---

# LLM Wiki Architect

Use this skill to turn a repository into a structured, maintainable knowledge
base for future agent work. The goal is not only to document the code, but to
make future edits start from an explicit owning module and boundary contract.

## Core Rule

Do not force every repository into `raw/`, `wiki/`, and `_templates/`.
Read the repository first, then adapt the wiki structure to its existing
documentation model.

Existing documentation systems can satisfy the wiki requirement when they give
future agents the same guarantees: a short entrypoint, a module-boundary map,
deep topic docs, local rules, and a checked drift policy. Do not create a new
wiki layer just because the files are named differently.

## Start Gate

Before changing code or docs:

1. Read local instructions: `AGENTS.md`, `CLAUDE.md`, nested instruction files,
   docs indexes, and tests that define documentation contracts.
2. Classify the repo:
   - docs-first repo,
   - Obsidian/LLM wiki repo,
   - mixed repo with generated module docs,
   - source-only repo.
3. Identify the owning module for the requested work.
4. Decide whether the work crosses module boundaries.
5. State which artifacts and verification commands must change.

If the owning module is unclear, update or propose the module-boundary contract
before editing implementation code.

When the request is an evaluation or field test, report the Start Gate result
before editing:

- repo classification,
- existing artifacts that already satisfy this skill,
- missing or weak artifacts,
- current docs-check failures,
- checker gaps found by independent scans,
- verification commands run or skipped with reasons.

## Artifact Policy

Required repo-local artifacts:

- A module-boundary document or equivalent with module owners,
  responsibilities, allowed edits, forbidden dependencies, and required tests.
- A repo-local wiki rule document explaining how this skill applies to the repo.

Equivalent artifacts are acceptable. For example, a repo may use root agent
instructions plus `.claude/architecture/`, `docs/OVERVIEW.md`, ADRs, and
docs-check scripts instead of `wiki/` files. In that case, improve the existing
system rather than adding a parallel one.

Conditional artifacts:

- `modules/*.md` detailed pages when the repo is large or the user requests a
  generated module index.
- `wiki/index.md`, `wiki/log.md`, and `wiki/hot.md` only when the repo opts into
  an Obsidian-style LLM wiki layout.

Generated module pages should include provenance, public API summary,
responsibility, mutation points, related modules, and wikilinks when the repo
uses Obsidian syntax.

## Update Workflow

1. Inventory entrypoints, runtime wiring, adapters, mutation points, and tests.
2. Compare existing docs against code and config before trusting them.
3. Write or refresh the module-boundary document.
4. Refresh generated module pages only when in scope.
5. Update the repo-local wiki rule if workflow or commands changed.
6. Record unresolved contradictions with an Obsidian callout only when the
   correct current truth cannot be determined.

For documentation evaluation passes, separate three classes of findings:

- current-document failures that should be fixed in the repo,
- missing enforcement that should become a checker or test,
- skill gaps that should improve this skill without hardcoding repo-specific
  facts.

## Verification

Prefer mechanisms over prompts:

- Run existing docs link and docs-quality tests when available.
- Run an independent conflict-marker scan over current docs and instruction
  files; do not assume the existing docs check catches merge artifacts.
- Check inline path references in current rule/index docs against the filesystem
  when the repo does not already enforce that mechanically.
- Treat stale "last verified commit" metadata as a review signal, not automatic
  failure, unless the repo declares it as a contract.
- Add or extend tests when the repo needs to enforce wiki artifacts.
- Add import or dependency contract tests only when boundaries are stable enough
  to enforce cheaply.
- Use `graphify update .` when installed and approved by repo policy.
- Use `graphify cluster-only . --no-viz` or record a skip reason when full graph
  refresh is too expensive or out of scope. If cluster-only fails because no
  graph exists yet, do not escalate to a full graph refresh unless the user's
  scope includes generating or updating graph artifacts.

NotebookLM or Obsidian notebooks may be used as optional reference input, but
local repository evidence remains the source of truth.

### Iterative Verification Loop

For implementation work, do not stop after one scan. Use a loop:

1. Run the narrowest existing check that exposes current drift.
2. If a checker gap is found, add a focused regression test and confirm it fails
   for the intended reason.
3. Implement the checker or doc fix.
4. Re-run the focused check.
5. Re-run the repo's docs-quality gate.
6. If the broader gate reveals a new drift class, repeat from step 1.

Completion requires the focused checks and the repo-local docs-quality gate to
pass, or a concrete skip reason tied to scope or environment.

### Continuation Handoff

When work remains, or the user asks to continue in the next session, leave a
handoff that a fresh agent can execute without chat history. Include:

- objective and current state,
- exact files changed or expected to change,
- RED/GREEN commands and outcomes,
- broader docs-quality gate outcome,
- remaining verification loops in priority order,
- explicit "do not claim complete until" gate,
- a paste-ready next-session prompt.

Prefer a repo-local handoff when the repository already uses durable handoff or
planning docs for agent continuity; otherwise use a temporary handoff file.

## Safety

- Never bulk-regenerate protected or untracked generated docs without explicit
  user approval.
- Never edit source code during a wiki-structure pass unless the user explicitly
  requested implementation work.
- Do not repair repo docs during an evaluation-only pass unless the user also
  asked for implementation.
- When improving this skill from a field test, add only generalizable process
  lessons. Do not bake one repository's filenames, commands, or temporary
  failures into the skill unless they are examples clearly marked as examples.
- Do not treat Graphify output as a substitute for reading source files.
- Preserve dirty worktrees and stage only intentional paths.

# Toolkit consolidation — integrate authored skills + hooks into the auto-pilot plugin

**Date:** 2026-05-29
**Status:** design (awaiting user review → writing-plans)
**Historical note (2026-06-06):** `llm-wiki-architect`, bundled by this consolidation, was later DELETED by the unified-coding-system merge; docs territory routes to `graphify-doc-rebuild` (→ `doc-management`). Mentions below are the 2026-05-29 record. See `docs/specs/2026-06-06-unified-coding-system-design.md`.
**Topic:** Reframe the `auto-pilot` plugin as "autonomous dev loop **+ personal toolkit**" and bundle the user's hand-authored skills and hooks into it so they are managed as one versioned plugin instead of loose `~/.claude/` files.

## 1. Goal

Stop maintaining the user's bespoke skills/hooks as loose, unmanaged files under `~/.claude/skills` and `~/.claude/hooks`. Bundle them into the existing `auto-pilot` plugin (which already has `.claude-plugin/plugin.json` + `marketplace.json` + `skills/` + `hooks/` + `agents/`), so they ship/version/install atomically.

auto-pilot keeps its name and its autonomous-dev-loop feature; it additionally becomes the home for the user's authored tooling.

## 2. Scope

### In — 9 authored skills → `auto-pilot/skills/`
- **Quality / dev (7):** `adversarial-review-loop`, `quality-eval`, `codebase-perfection-loop`, `setup-harness`, `doc-drift-audit`, `llm-wiki-architect`, `improve-codebase-architecture`
- **Debug (2):** `diagnosing-llm-output-leaks`, `diagnosing-stale-runtime`

### In — 6 authored hooks → `auto-pilot/hooks/`
- `guard-destructive.py`, `codex-conductor-guard.py`, `session-skill-profile.py`
- `cleanup-root-png.sh`, `cleanup-orphan-mcp.sh`, `cleanup-gh-actions.sh`
- (plus their `test_*.py` siblings where present)

### In — 1 standalone agent → `auto-pilot/agents/`
- `code-perfector` (generic Python code-quality agent, authored)
- (`~/.claude/agents/` also holds `rpc-schema-validator` — ambiguous/Supabase, **deferred** — and `sportic365-contract-drift-checker` — sportic365 private, **excluded**.)

### Out (explicitly excluded)
- `sportic-research`, `sportic-contents` — sportic365 **private project** tooling; kept separate (future `sportic` plugin).
- Installed/vendored/mirror skills: gstack suite (~50), `graphify`, `notebooklm`, `huashu-design`, `canvas-design`, insforge*, `mcp2cli`, `cua-driver`, `article-magazine`, `find-skills` — NOT the user's to bundle.
- Ambiguous (`grill-me`, `codex-orchestra`) — deferred until provenance confirmed.

## 3. Decisions (locked)

| Decision | Choice |
|---|---|
| Container | `auto-pilot` plugin, reframed as autonomous-loop **+ personal toolkit**; name kept |
| Copy vs move | **COPY** (non-destructive). `~/.claude` originals untouched until the bundled copies are verified, then a later decommission pass removes loose duplicates |
| sportic | excluded |
| Procedure | spec → user review → writing-plans → TDD implementation |
| Version | `plugin.json` 0.3.0 → 0.4.0; description updated |

## 4. Target structure

```
auto-pilot/
├── .claude-plugin/plugin.json        # name kept, version 0.4.0, description += "+ personal toolkit"
├── .claude-plugin/marketplace.json   # sync version/description
├── skills/
│   ├── auto-pilot/                    # existing entry skill
│   ├── adversarial-review-loop/       # + scripts/arl-helpers.sh, tests/*.bats
│   ├── quality-eval/
│   ├── codebase-perfection-loop/      # + references/*.md
│   ├── setup-harness/                 # + scripts/ references/ templates/ agents/ commands/ (~68 files)
│   ├── doc-drift-audit/               # + scripts/check-doc-reference-integrity.mjs
│   ├── llm-wiki-architect/
│   ├── improve-codebase-architecture/ # + LANGUAGE.md INTERFACE-DESIGN.md DEEPENING.md
│   ├── diagnosing-llm-output-leaks/
│   └── diagnosing-stale-runtime/
├── hooks/
│   ├── hooks.json                     # + register the 6 authored hooks with matchers
│   ├── (existing 5 auto-pilot hooks)
│   ├── guard-destructive.py + test_guard_destructive.py
│   ├── codex-conductor-guard.py + test_codex_conductor_guard.py
│   ├── session-skill-profile.py + test_session_skill_profile.py
│   └── cleanup-{root-png,orphan-mcp,gh-actions}.sh
└── agents/                            # existing 10; + code-perfector (from ~/.claude/agents/)
```

## 5. Required fixups after COPY (this is the real work, not just file copy)

1. **Absolute cross-references break on move.** Scan every bundled skill for `~/.claude/skills/...` and `/Users/lyan/.claude/...` absolute paths and repoint:
   - `adversarial-review-loop` reads `~/.claude/skills/quality-eval/SKILL.md` as the rubric SoT → repoint to `${CLAUDE_PLUGIN_ROOT}/skills/quality-eval/SKILL.md` (both now co-bundled).
   - `setup-harness` has **~10 files** carrying `~/.claude` absolute refs (largest fixup of the set). Internal skill/script refs → repoint to `${CLAUDE_PLUGIN_ROOT}`; the `@~/.claude/docs/harness-engineering.md` external-doc citation **stays global** (not vendored).
   - `llm-wiki-architect`, `codebase-perfection-loop` reference other skills (`graphify`, `adversarial-review-loop`) → graphify stays global (reference unchanged); ARL is co-bundled (make relative).
2. **Hook path rewrite.** `settings.json` wires hooks by absolute path (`python3 /Users/lyan/.claude/hooks/guard-destructive.py`). In `auto-pilot/hooks/hooks.json` they must use `${CLAUDE_PLUGIN_ROOT}/hooks/<file>` and be `chmod +x`.
3. **Hook matcher parity.** Port the matchers from `settings.json` (PreToolUse for guard-destructive + codex-conductor-guard + cleanup-*; SessionStart for session-skill-profile) into `hooks.json` exactly.

## 6. Hook scope change (must understand)

- Today the 6 hooks live in `~/.claude/settings.json` → they fire on **every session, globally**.
- As plugin hooks they fire **whenever the auto-pilot plugin is enabled**. If the plugin is always enabled this is equivalent; if not, coverage narrows.
- **Mitigation:** keep the originals in `settings.json` for now (do NOT delete). Accept temporary double-registration; resolve in the later decommission pass once plugin-enabled-always is confirmed. Double-firing risk: the cleanup hooks are idempotent; `guard-destructive` is read-only-decision so double-eval is harmless.

## 7. Testing / verification

- `plugin.json` + `marketplace.json` valid JSON, version synced.
- Each bundled skill: frontmatter has `name` + `description`; no remaining dead `~/.claude` absolute refs (grep clean).
- `hooks.json` schema valid; every referenced hook file exists and is `chmod +x`; matchers parity-checked vs `settings.json`.
- Existing auto-pilot suite stays green: `pytest tests/ -q` (currently 202 passed), `mypy scripts/`, `ruff check`.
- Bundled hook self-tests run: `guard-destructive`, `codex-conductor-guard`, `session-skill-profile` test files pass under the plugin path.
- Plugin discovery smoke: the 9 new skills resolve under the plugin namespace.

## 8. Risks / limits

- **Cross-ref breakage** (§5) is the main failure mode — a moved skill silently pointing at the now-stale `~/.claude` copy. Grep-gated.
- **Duplicate skills** (plugin copy + loose global) until the decommission pass — both may trigger; acceptable short-term, flagged for cleanup.
- **Repo growth**: setup-harness alone adds ~68 files; total well within reason. sportic (146+83) excluded partly for this reason.
- **Identity dilution**: auto-pilot is no longer single-purpose. Accepted by user decision; description updated to say so.
- **Not addressed here:** decommissioning `~/.claude` originals, removing duplicate `settings.json` hook registrations, sportic plugin, gstack 1GB bloat — separate follow-ups.

## 9b. Adversarial review revisions (2026-05-29, cold-Claude verified; Codex pending)

Dual adversarial review found the §1–§8 plan **change-first** (P0×2, P1×5). All load-bearing claims verified on disk. The plan is RE-SCOPED:

- **DROP `setup-harness` from the bundle.** It is already its own nested plugin (`.claude-plugin/plugin.json` v2.0.0 + `agents/`×3 + `commands/`×8). A skill subtree does **not** carry agents/commands (CC resolves those at plugin root only), so bundling it as `skills/setup-harness/` silently drops 11 components. It stays a separate plugin. → **8 skills**, not 9.
- **Hooks: bundle only the 2 decision guards** — `guard-destructive.py`, `codex-conductor-guard.py` (double-fire harmless). **EXCLUDE**: `cleanup-gh-actions.sh` (destructive, `ORG="MoneyPick-KO"`, `gh run delete` — must never ship), `cleanup-orphan-mcp.sh` (hardcoded personal MCP list), `cleanup-root-png.sh` (personal-workflow Stop hook), `session-skill-profile.py` (coupled to the global `~/.claude/skills` on/off layout it advertises — no plugin value).
- **Path fixups are NOT `${CLAUDE_PLUGIN_ROOT}` swaps.** That var only expands in `hooks.json` command strings + the manifest — NOT inside skill bodies, helper scripts, or markdown. Fix via the existing `$SKILL_DIR` self-location pattern / relative paths. For `adversarial-review-loop`'s rubric path embedded in a `codex exec` prompt literal, the PM must resolve the absolute co-bundled path at runtime before spawning Codex.
- **Duplicate-skill ambiguity:** instead of "leave originals, decommission later," flip the global copies to `off` in `settings.json` (`quality-eval`, others currently `on`) in the same change — reversible, removes resolver ambiguity, no file deletion.
- **Hook test paths:** `test_codex_conductor_guard.py:26` and `test_guard_destructive.py:13` hardcode `/Users/lyan/.claude/hooks/...` → repoint to `Path(__file__).parent`. And **wire `hooks/` into the CI gate** (pytest/mypy/ruff scope currently exclude it) or the "tests pass" claim is vacuous; expect new lint/type fixes on the copied code.
- **Agent collision + manifest:** dedupe `code-perfector` + (no setup-harness agents now) against the existing 10 agents by filename; field-sync `marketplace.json` (version + toolkit description/keywords).

Revised bundle: **8 skills + 2 hooks + 1 agent (code-perfector)**. §2/§5/§6/§7 above are superseded by this section where they conflict.

### Codex-verified additions (Codex run stalled mid-search but surfaced 3 high-value signals; all verified on disk)

- **P0 — auto-pilot is not a valid, installed plugin yet.** `claude plugin validate .` **fails**: `plugins.0.source: Invalid input` in `marketplace.json` (`"source": "."` is not a valid source form), and the manifests drift on version (`marketplace.json` 0.1.0 vs `plugin.json` 0.3.0). Also auto-pilot is **absent from `~/.claude/plugins/installed_plugins.json`** — the plugin has never been installed. **Consequence:** bundling skills/hooks into an uninstalled, non-validating plugin is INERT — nothing loads. This is a **prerequisite Phase 0** nobody had.
- **P0 — plugin skills are namespaced `/<plugin>:<skill>`.** Bundled skills become `auto-pilot:quality-eval` etc. Any skill that triggers on / cross-references a BARE name (e.g. `adversarial-review-loop` reading `quality-eval`) must be made namespace-aware, not just path-aware.
- Confirms Claude's hook/duplicate findings independently.

### Required phasing (supersedes "just copy")

- **Phase 0 (prerequisite):** fix `marketplace.json` `source` to a valid form + sync version to `plugin.json` (0.4.0) → `claude plugin validate .` passes → install the plugin (marketplace add / install) → confirm it loads (skills/hooks/agents discoverable). Until this is green, consolidation has zero observable effect. This is also the genuine "prove the plugin works live" gate.
- **Phase 1:** bundle the 8 skills + 2 hooks + 1 agent with the §9b fixups (namespace-aware cross-refs, `$SKILL_DIR` paths, relative test paths, hooks/ in CI scope, globals flipped `off`).

## 9. Non-goals

- No plugin GENERATOR (the earlier `plugin-forge` idea is dropped — this is a one-time manual consolidation).
- No skill content rewrites beyond the §5 path fixups.
- No deletion of originals in this iteration.

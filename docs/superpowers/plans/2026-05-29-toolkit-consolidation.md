# Toolkit Consolidation Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle the user's 8 authored skills + 2 authored hooks + 1 agent into the `auto-pilot` plugin (v0.4.0), with the cross-ref/path/test fixups the dual adversarial review required, so they are managed as one installed plugin.

**Architecture:** Non-destructive COPY of authored components into the plugin tree; repoint absolute `~/.claude` refs to plugin-relative paths; register hooks in `hooks/hooks.json` with `${CLAUDE_PLUGIN_ROOT}` + matchers ported from `settings.json`; wire `hooks/` into the CI gate; bump version; flip the global duplicate skills `off`; reinstall the plugin from its local marketplace and verify it validates + loads. The installed plugin is a **cache snapshot** (`~/.claude/plugins/cache/auto-pilot-marketplace/auto-pilot/<version>`), so changes only take effect after a version bump + reinstall.

**Tech Stack:** Claude Code plugin (skills/agents/hooks + `.claude-plugin/{plugin,marketplace}.json`), bash, Python (pytest/mypy/ruff), `claude plugin validate|marketplace|install`.

**Spec:** `docs/superpowers/specs/2026-05-29-toolkit-consolidation-design.md` (§9b is authoritative where it conflicts with §2–§7).

**Scope guard — bundle exactly these:**
- Skills (8): `adversarial-review-loop`, `quality-eval`, `codebase-perfection-loop`, `doc-drift-audit`, `llm-wiki-architect`, `improve-codebase-architecture`, `diagnosing-llm-output-leaks`, `diagnosing-stale-runtime`
- Hooks (2): `guard-destructive.py`, `codex-conductor-guard.py` (+ their `test_*.py`)
- Agent (1): `code-perfector`
- **Excluded** (do NOT bundle): `setup-harness` (nested plugin), `cleanup-*.sh` (destructive/personal), `session-skill-profile.py` (global-coupled), `sportic-*`, `rpc-schema-validator`, `sportic365-contract-drift-checker`.

## File structure

```
auto-pilot/
├── .claude-plugin/plugin.json         # MODIFY: version 0.4.0, description += toolkit
├── .claude-plugin/marketplace.json    # MODIFY: version 0.4.0, description
├── skills/
│   ├── auto-pilot/                    # unchanged
│   └── <8 new skill dirs>             # CREATE (copied, caches stripped, abs refs fixed)
├── hooks/
│   ├── hooks.json                     # MODIFY: register 2 hooks + matchers
│   ├── guard-destructive.py           # CREATE (copy)
│   ├── test_guard_destructive.py      # CREATE (copy, HOOK path fixed)
│   ├── codex-conductor-guard.py       # CREATE (copy)
│   └── test_codex_conductor_guard.py  # CREATE (copy, HOOK path fixed)
├── agents/code-perfector.md           # CREATE (copy)
├── mypy.ini                           # MODIFY: add hooks to type-check scope
└── (CLAUDE.md testing block)          # MODIFY: note hooks/ in lint/test scope
```

---

### Task 1: Copy the 8 skills into the plugin (caches stripped)

**Files:**
- Create: `skills/{adversarial-review-loop,quality-eval,codebase-perfection-loop,doc-drift-audit,llm-wiki-architect,improve-codebase-architecture,diagnosing-llm-output-leaks,diagnosing-stale-runtime}/`

- [ ] **Step 1: Copy each skill dir, excluding caches**

```bash
cd /Users/lyan/Documents/Project/auto-pilot
for s in adversarial-review-loop quality-eval codebase-perfection-loop doc-drift-audit \
         llm-wiki-architect improve-codebase-architecture \
         diagnosing-llm-output-leaks diagnosing-stale-runtime; do
  rsync -a --exclude='__pycache__' --exclude='.pytest_cache' --exclude='.ruff_cache' \
        --exclude='.git' "$HOME/.claude/skills/$s/" "skills/$s/"
done
```

- [ ] **Step 2: Verify all 8 present with a SKILL.md**

Run:
```bash
for s in adversarial-review-loop quality-eval codebase-perfection-loop doc-drift-audit \
         llm-wiki-architect improve-codebase-architecture \
         diagnosing-llm-output-leaks diagnosing-stale-runtime; do
  test -f "skills/$s/SKILL.md" && echo "OK $s" || echo "MISSING $s"
done
```
Expected: 8 lines all `OK`.

- [ ] **Step 3: Verify no cache dirs leaked in**

Run: `find skills -name '__pycache__' -o -name '.pytest_cache' -o -name '.ruff_cache' | grep -v skills/auto-pilot`
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add skills/
git commit -m "feat(toolkit): bundle 8 authored skills into the plugin (copy)"
```

---

### Task 2: Fix absolute `~/.claude` cross-refs in bundled skills

**Files:**
- Modify: any bundled `skills/*` file containing `~/.claude` / `/Users/lyan/.claude`

- [ ] **Step 1: Find all absolute refs in the 8 bundled skills**

Run:
```bash
grep -rnE "~/\.claude/|/Users/lyan/\.claude/" skills/ | grep -v 'skills/auto-pilot/'
```
Expected: a small list. The known one is `adversarial-review-loop` referencing `~/.claude/skills/quality-eval/SKILL.md` (rubric source of truth), appearing in the SKILL body and inside a `codex exec` prompt literal.

- [ ] **Step 2: Repoint the adversarial-review-loop rubric reference to the co-bundled skill**

In `skills/adversarial-review-loop/SKILL.md`, replace every `~/.claude/skills/quality-eval/SKILL.md` (and `/Users/lyan/.claude/skills/quality-eval/SKILL.md`) with the co-bundled relative path `../quality-eval/SKILL.md`. For the line that builds a `codex exec "...Inputs: ...quality-eval/SKILL.md..."` prompt, change it to resolve the absolute path at runtime before spawning — i.e. the skill instructs: "resolve `$(cd "$(dirname SKILL.md)/../quality-eval" && pwd)/SKILL.md` and pass that absolute path into the Codex prompt." Concretely, edit the prompt-construction line to read:

```
Rubric source: the co-bundled quality-eval skill at ../quality-eval/SKILL.md
(when spawning Codex, resolve this to an absolute path first — Codex runs in a
separate process without ${CLAUDE_PLUGIN_ROOT}).
```

- [ ] **Step 3: Fix any other found absolute refs to plugin-relative**

For each remaining hit from Step 1, replace `~/.claude/skills/<x>` with `../<x>` if `<x>` is co-bundled, or leave it (and add a one-line note) if `<x>` is a still-global skill (e.g. `graphify`, which is NOT bundled).

- [ ] **Step 4: Verify no co-bundled skill is referenced by a stale absolute path**

Run:
```bash
grep -rnE "~/\.claude/skills/(adversarial-review-loop|quality-eval|codebase-perfection-loop|doc-drift-audit|llm-wiki-architect|improve-codebase-architecture|diagnosing-llm-output-leaks|diagnosing-stale-runtime)" skills/ | grep -v 'skills/auto-pilot/'
```
Expected: no output (all co-bundled cross-refs now relative).

- [ ] **Step 5: Commit**

```bash
git add skills/
git commit -m "fix(toolkit): repoint bundled-skill cross-refs to plugin-relative paths"
```

---

### Task 3: Bundle + register the 2 decision hooks

**Files:**
- Create: `hooks/guard-destructive.py`, `hooks/test_guard_destructive.py`, `hooks/codex-conductor-guard.py`, `hooks/test_codex_conductor_guard.py`
- Modify: `hooks/hooks.json`

- [ ] **Step 1: Copy the 2 hooks + their tests**

```bash
cd /Users/lyan/Documents/Project/auto-pilot
cp "$HOME/.claude/hooks/guard-destructive.py" hooks/
cp "$HOME/.claude/hooks/test_guard_destructive.py" hooks/
cp "$HOME/.claude/hooks/codex-conductor-guard.py" hooks/
cp "$HOME/.claude/hooks/test_codex_conductor_guard.py" hooks/
chmod +x hooks/guard-destructive.py hooks/codex-conductor-guard.py
```

- [ ] **Step 2: Fix the hardcoded absolute HOOK paths in the copied tests**

In `hooks/test_guard_destructive.py` replace:
```python
HOOK = "/Users/lyan/.claude/hooks/guard-destructive.py"
```
with:
```python
from pathlib import Path
HOOK = str(Path(__file__).parent / "guard-destructive.py")
```
In `hooks/test_codex_conductor_guard.py` replace:
```python
HOOK = "/Users/lyan/.claude/hooks/codex-conductor-guard.py"
```
with:
```python
from pathlib import Path
HOOK = str(Path(__file__).parent / "codex-conductor-guard.py")
```
(If the file already imports `pathlib`, don't duplicate the import.)

- [ ] **Step 3: Run the two copied hook tests against the bundled copies**

Run: `python3 -m pytest hooks/test_guard_destructive.py hooks/test_codex_conductor_guard.py -q`
Expected: PASS (now exercising the plugin copies, not the global originals).

- [ ] **Step 4: Read the global hook registrations to copy the matchers**

Run: `sed -n '180,238p' "$HOME/.claude/settings.json"`
Note the matcher(s) under `PreToolUse` for `guard-destructive.py` and `codex-conductor-guard.py` (tool-name matchers).

- [ ] **Step 5: Register the 2 hooks in `hooks/hooks.json` using `${CLAUDE_PLUGIN_ROOT}`**

Add to the existing `PreToolUse` array in `hooks/hooks.json` (match the matchers found in Step 4; example shape):
```json
{
  "matcher": "Bash",
  "hooks": [
    { "type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/guard-destructive.py" }
  ]
},
{
  "matcher": "Bash",
  "hooks": [
    { "type": "command", "command": "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/codex-conductor-guard.py" }
  ]
}
```
(Use the exact matchers from settings.json, not a guess.)

- [ ] **Step 6: Verify hooks.json is valid JSON**

Run: `python3 -c "import json; json.load(open('hooks/hooks.json')); print('ok')"`
Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
git add hooks/
git commit -m "feat(toolkit): bundle guard-destructive + codex-conductor-guard hooks (relative test paths, plugin-root wiring)"
```

---

### Task 4: Bundle the code-perfector agent

**Files:**
- Create: `agents/code-perfector.md`

- [ ] **Step 1: Confirm no name collision with the existing 10 agents**

Run: `ls agents/ | grep -i code-perfector || echo "no collision"`
Expected: `no collision`.

- [ ] **Step 2: Copy the agent**

```bash
cp "$HOME/.claude/agents/code-perfector.md" agents/code-perfector.md
```

- [ ] **Step 3: Verify it has valid frontmatter (name + description)**

Run: `head -8 agents/code-perfector.md`
Expected: YAML frontmatter with `name:` and `description:`.

- [ ] **Step 4: Commit**

```bash
git add agents/code-perfector.md
git commit -m "feat(toolkit): bundle code-perfector agent"
```

---

### Task 5: Wire `hooks/` into the CI gate

**Files:**
- Modify: `mypy.ini`
- Modify: `CLAUDE.md` (testing block — document hooks/ in scope)

- [ ] **Step 1: Add hooks to mypy scope**

In `mypy.ini`, change `files = scripts` to `files = scripts, hooks`.

- [ ] **Step 2: Run mypy over the new hooks; fix any type errors**

Run: `python3 -m mypy scripts hooks 2>&1 | tail -20`
Expected: clean, or a short list of type errors in the copied hooks. Fix each minimally (add type hints / `# type: ignore[code]` only where a third-party stub is genuinely missing). Re-run until clean.

- [ ] **Step 3: Run ruff over hooks; fix lint**

Run: `python3 -m ruff check scripts tests hooks 2>&1 | tail -20`
Expected: clean or a short list. Fix; re-run until clean.

- [ ] **Step 4: Confirm pytest now collects the hook tests**

Run: `python3 -m pytest hooks/ -q 2>&1 | tail -5`
Expected: the bundled hook tests pass.

- [ ] **Step 5: Update CLAUDE.md testing block**

In `CLAUDE.md`, in the Testing section, change the mypy/ruff lines to include `hooks`:
```bash
python3 -m mypy scripts/ hooks/
python3 -m ruff check scripts/ tests/ hooks/
```
and add a line: `python3 -m pytest hooks/ -q  # bundled hook self-tests`.

- [ ] **Step 6: Run the full gate**

Run: `python3 -m pytest tests/ hooks/ -q && python3 -m mypy scripts hooks && python3 -m ruff check scripts tests hooks`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add mypy.ini CLAUDE.md
git commit -m "ci(toolkit): wire hooks/ into mypy + ruff + pytest scope"
```

---

### Task 6: Bump version + update manifests

**Files:**
- Modify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: Bump plugin.json to 0.4.0 + extend description**

In `.claude-plugin/plugin.json` set `"version": "0.4.0"` and append to the description: ` Also bundles the author's quality/review, harness-doc, and debugging skills + safety hooks as a personal toolkit.`

- [ ] **Step 2: Sync marketplace.json**

In `.claude-plugin/marketplace.json` set the plugin entry `"version": "0.4.0"` and update its `"description"` to match.

- [ ] **Step 3: Validate**

Run: `claude plugin validate .`
Expected: `✔ Validation passed` (no errors).

- [ ] **Step 4: Commit**

```bash
git add .claude-plugin/
git commit -m "chore(toolkit): bump to 0.4.0 + manifest descriptions"
```

---

### Task 7: Flip the global duplicate skills `off`

**Files:**
- Modify: `~/.claude/settings.json` (NOT in the repo — user-global)

- [ ] **Step 1: Inspect current skillOverrides**

Run: `python3 -c "import json;d=json.load(open('$HOME/.claude/settings.json'));print(json.dumps(d.get('skillOverrides',{}),indent=2))"`

- [ ] **Step 2: Set the 8 bundled skill names to "off" so the plugin copies are the only live ones**

Edit `~/.claude/settings.json` `skillOverrides` to add/set each of the 8 skill names to `"off"`:
`adversarial-review-loop, quality-eval, codebase-perfection-loop, doc-drift-audit, llm-wiki-architect, improve-codebase-architecture, diagnosing-llm-output-leaks, diagnosing-stale-runtime` → `"off"`.
(Reversible — flips them back on if the consolidation is abandoned. Originals on disk untouched.)

- [ ] **Step 3: Verify settings.json still valid JSON**

Run: `python3 -c "import json; json.load(open('$HOME/.claude/settings.json')); print('ok')"`
Expected: `ok`.

(No commit — this file is outside the repo.)

---

### Task 8: Reinstall the plugin + verify load

**Files:** none (operates on the installed cache)

- [ ] **Step 1: Update the local marketplace + reinstall to pick up 0.4.0**

Run:
```bash
claude plugin marketplace update auto-pilot-marketplace 2>&1 | tail -3
claude plugin install auto-pilot@auto-pilot-marketplace 2>&1 | tail -3
```
Expected: success; install path now ends in `/0.4.0`.

- [ ] **Step 2: Verify the cache has the new components at 0.4.0**

Run:
```bash
P="$HOME/.claude/plugins/cache/auto-pilot-marketplace/auto-pilot/0.4.0"
echo "skills:"; ls "$P/skills/" | wc -l        # expect 9 (auto-pilot + 8)
echo "hooks py:"; ls "$P/hooks/"*.py | wc -l    # expect the bundled hooks present
echo "agents:"; ls "$P/agents/" | grep -c code-perfector  # expect 1
```
Expected: skills 9, code-perfector present.

- [ ] **Step 3: Confirm enabled**

Run: `claude plugin list 2>&1 | grep -iA3 auto-pilot | head`
Expected: `Version: 0.4.0`, `Status: ✔ enabled`.

---

### Task 9: Final verification + PR

- [ ] **Step 1: No stale co-bundled absolute refs remain**

Run: `grep -rnE "~/\.claude/skills/(quality-eval|adversarial-review-loop)" skills/ | grep -v auto-pilot`
Expected: no output.

- [ ] **Step 2: Full gate green**

Run: `python3 -m pytest tests/ hooks/ -q && python3 -m mypy scripts hooks && python3 -m ruff check scripts tests hooks && claude plugin validate .`
Expected: all green / `✔ Validation passed`.

- [ ] **Step 3: Push + open PR**

```bash
git push
gh pr create --base main --title "feat: bundle authored skills+hooks into auto-pilot (toolkit, v0.4.0)" \
  --body "Implements docs/superpowers/specs/2026-05-29-toolkit-consolidation-design.md (Phase 1). 8 skills + 2 hooks + code-perfector agent bundled; cross-refs/test-paths/CI fixed; globals flipped off; plugin validates + reinstalls at 0.4.0."
```

---

## Self-review notes

- **Spec coverage:** §9b re-scope (8/2/1, drop setup-harness, exclude destructive hooks) → Tasks 1/3/4 scope guard. Path fixups (`$SKILL_DIR`/relative, not `${CLAUDE_PLUGIN_ROOT}` in bodies) → Task 2. Namespace-aware cross-ref → Task 2 Step 2. Hook test paths → Task 3 Step 2. CI wiring → Task 5. Global-off → Task 7. Phase-0 validate/install prerequisite already DONE (committed `b4b6ea3`); Task 6/8 carry it to 0.4.0. Codex namespacing finding → Task 2 (relative refs) + accepted that bundled skills are invoked as `auto-pilot:<name>`.
- **Residual risk:** the adversarial-review-loop → Codex-subprocess rubric path (Task 2 Step 2) is the one place a relative path is insufficient; the fix relies on the skill resolving an absolute path at spawn time — verify by reading the edited prompt-construction line, not just grep. bats tests for ARL are not wired into the Python gate (need `bats`); Task 5 covers Python tests only — note this gap rather than claim ARL's bats run in CI.

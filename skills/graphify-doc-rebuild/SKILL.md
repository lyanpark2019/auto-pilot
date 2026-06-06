---
name: graphify-doc-rebuild
description: "Use when the user says docs are rotten/patchwork ('문서 개판', 'doc rot', 'docs don't match code', 'rebuild docs from code', 'graphify-native docs', '문서 전면 재작성'), or after a big refactor/migration when hand-maintained structure docs have drifted. Diagnose first — if audits show the tree is disciplined, do targeted cleanup, not a full rebuild."
---

# graphify-doc-rebuild

Rebuild a repo's documentation so it CAN'T rot the same way again. The failure mode: hand-maintained structure docs (per-module wikis, "what-calls-what" pages) ALWAYS drift because nothing forces them to match code. The fix is a split model.

## The model

| Layer | Source of truth | Who writes it |
|-------|-----------------|---------------|
| **What** (structure: modules, call graph, deps) | the **code graph** (graphify Tree-sitter AST) — queried/generated, never hand-typed | machine + `graphify query`/`explain` |
| **Why** (decisions, incidents, gotchas, governance) | hand-written, harvested from old docs + memory, every entry cites a source | human/agent, faithful-extraction-only |
| **Generated mirror** (repo `.claude/`, `docs/`) | rewritten FROM the above two, with `file:line` cites | agents, then adversarially verified |

Proven end-to-end on PickL-API 2026-06-06 (graph 22937 → ≈3.3k product nodes; review round 1 = REJECT with a P0 the author could not self-detect, round 2 = APPROVE).

## Per-repo discovery (do this before Phase 6/7 — these vary by repo)

| Slot | How to find |
|------|-------------|
| `<LOCAL_GATE>` — full local completion gate | repo CLAUDE.md / CI workflow (e.g. `bash app/scripts/ops/verify_quality_gate.sh --mode full`) |
| `<REF_GUARD>` — doc→source ref-integrity script | `rg -l 'DOC_ROOTS|doc.*source.*ref' <repo>` (repo-wide, plain `|`) — may not exist yet (Phase 6 creates it) |
| `<DEPLOY_GOVERNANCE>` — merge/deploy contract page | repo CLAUDE.md governance section; check CI for `push:[main]` deploy triggers |
| `<MEMORY_DIR>` — session auto-memory | `~/.claude/projects/<project-slug>/memory/` |

## Red flags — when NOT to full-rebuild

Run Phase 0 FIRST. **Phase 0 is a hard gate**: only a `patchwork` verdict unlocks Phases 1–7; a `disciplined` verdict exits to targeted cleanup. Most rot is narrow:

| Audit finding | Action |
|---------------|--------|
| Canonical tree is disciplined, rot is in scratch dirs / `.planning/` | delete the scratch, keep the tree — STOP here |
| One fact duplicated across N files, rest accurate | collapse to single-SoT page + one-line cites — STOP here |
| Un-distilled handoff plans/specs piling up | distill → ADR, delete the plan — STOP here |
| Only a few dead `file:line` refs | mechanical guard fix, no rewrite — STOP here |
| Genuinely patchwork: stale policies as current, per-module wikis drifting, structure hand-typed | **full rebuild — proceed to Phase 1** |

"The user thinks it's rotten" is a hypothesis, not a finding. Diagnose before demolishing.

## Phases

### 0. Diagnose — parallel read-only audit (don't assume rot)
Dispatch 2-3 read-only audit agents in ONE message (max parallel):
- **contradiction scan** — fact stated differently across docs; stale policy described as current.
- **structure health** — per-module wikis vs reality; dead refs; orphan pages.
- **git-history** — what changed recently that docs lag behind; churn-prone files.

Output: ranked **P0/P1/P2** findings + an explicit verdict line: `disciplined` (→ targeted cleanup, STOP) or `patchwork` (→ proceed).

### 1. Build the code-only product graph (structure SoT)
graphify Pass 1 is deterministic Tree-sitter AST, but the **full corpus ingests `.md` + rationale nodes → stale-doc bleed into the graph**, plus json/sh/test/scratch noise. Filter to code:

```bash
# 1. build or refresh the graph — AST-only, no LLM key needed:
graphify update .          # re-extracts code files; works with zero API keys
# (a FIRST-ever full build `graphify .` runs semantic LLM passes and needs an API key —
#  for this skill the AST layer from `update` is sufficient; reuse graphify-out/ if present)

# 2. filter graph.json: keep ONLY product code.
#    file_type=="code" is NECESSARY but NOT SUFFICIENT (json/sh/test nodes carry it too)
python3 - <<'PY'
import json, pathlib
g = json.load(open("graphify-out/graph.json"))
ek = "links" if "links" in g else "edges"     # networkx emits "links"
def keep(n):
    sf = (n.get("source_file") or "")
    return (n.get("file_type")=="code"
            and sf.endswith(".py")                       # adjust per language
            and "/tests/" not in sf and not sf.endswith("_test.py")
            and ".planning/" not in sf and ".vault-builder/" not in sf)
g["nodes"] = [n for n in g["nodes"] if keep(n)]
ids = {n["id"] for n in g["nodes"]}
g[ek] = [e for e in g[ek] if e["source"] in ids and e["target"] in ids]
# cluster-only resolves <dir>/graphify-out/graph.json — write the CANONICAL layout:
out = pathlib.Path("/tmp/code-only/graphify-out"); out.mkdir(parents=True, exist_ok=True)
json.dump(g, open(out/"graph.json","w"))
print("nodes:", len(g["nodes"]))
PY

# 3. recluster the filtered graph (no .md bleed)
graphify cluster-only /tmp/code-only --no-viz
```

**Validate the filter worked** — a domain query must return real domain classes, not fixtures:
```bash
graphify query "where are credits earned and quota enforced" --graph /tmp/code-only/graphify-out/graph.json
# → domain services (good)   NOT test fixtures / scratch json (filter failed — adjust paths, re-run)
```

### 2. Assemble a vault workbench
A scratch KB dir (Obsidian or any folder) — NOT the repo yet:
- `_graph/` — `graph.json` + `GRAPH_REPORT.md` + `graphify tree --graph <filtered>` (HTML) + `graphify export callflow-html`.
- `intent/` — the **Why harvest**. Parallel agents extract from old docs + memory:
  `decisions` (ADRs), `gotchas`, `history`, `governance`.
  **Rules:** every entry cites its source; **faithful-extraction-only — never invent a rationale**; if the why isn't recorded, write `(why not documented)`. This BEFORE deleting anything — "none lost" invariant (decisions/incidents are NOT in the call graph).

### 3. Author topic/design docs FROM the graph
One agent per subsystem. Method, in order:
1. `graphify query "<subsystem question>"` / `graphify explain <symbol>` (with `--graph <filtered>`) → get the real files.
2. **READ the actual source files the graph surfaces.**
3. Write the doc with `file:line` cites; weave Why from `intent/`.

Top-down by subsystem (~8-10 docs), **NOT per-module** — per-module pages are the rot machine. The read-the-source step catches stale facts (nonexistent files cited, dormant modules described as active, fixed bugs documented as broken).

### 4. Rewrite the repo doc trees from the vault
- `.claude/design/` ← the topic docs from Phase 3.
- `.claude/rules/` ← **single-SoT governance** (ONE canonical page states the deploy/merge/approval rule; every other doc cites it in one line, never restates).
- `architecture/` ← slim to **cross-cutting rules only** (layer/import invariants). Structure detail = the graph's job. Retain any load-bearing threshold a stub would orphan.
- root `CLAUDE.md` ← nav index pointing at graph + design + rules.
- `docs/` ← abstract human entry; archive superseded pages to `docs/_archive/` (mark guard-exempt).
- **Delete hand-written per-module wikis** — git keeps the history.
- **Dangling-ref sweep** (all three classes): `rg -n "llm-wiki|<retired-tree-name>" .claude docs *.md` → repoint or delete every ref to the deleted wiki; repoint vault-relative cites (`intent/...`) to repo paths; convert `[[wikilinks]]` → `[text](path)`. Re-run the markdown link gate after.

### 5. MANDATORY dual adversarial review — until APPROVE
Dispatch in parallel, in one message:
- **Codex-adversarial** reviewer, and
- **cold Claude** reviewer (fresh context).

Their job: **open every cited file and refute every claim.** Fix ALL P0/P1. Re-review until BOTH return APPROVE with zero new findings. The author's self-assessment is worthless here — the author structurally cannot see their own P0s. **This step is not optional and not self-servable.**

### 6. Lock anti-re-rot
- **Mechanical guard** (`<REF_GUARD>`): cited paths resolve, `file:NNN` ≤ EOF, `` `file.py` → `SYMBOL` `` anchors resolve, `RETIRED_SYMBOLS` denylist blocks reintroduced dead names (add the retired wiki/alias names you just deleted). **Edit its `DOC_ROOTS` to the NEW doc roots** (drop deleted trees, add `.claude/design`), keep `docs/_archive/` exempt. If no guard exists, create one and wire it into `<LOCAL_GATE>`.
- `graphify hook install` — post-commit auto-rebuild so the structure SoT never lags code (`graphify hook status` to confirm).
- **Document the guard's blind spots** (mechanical, not semantic): `.md→.md` line cites, range upper bounds, valid-but-wrong-line cites. Mitigate with symbol anchors / section-name cites + the Phase 5 review + periodic `/doc-drift-audit`.

### 7. Ship tail — gate, commit, boundary, handoff
1. `<LOCAL_GATE>` → must EXIT 0 (the rewrite touched guard config + doc tests).
2. Commit on a docs branch (`docs/<topic>`); never directly on main.
3. **Deploy boundary — check `<DEPLOY_GOVERNANCE>` BEFORE merging:** if the repo's CI deploys on `push:[main]` with **no path filter** (common), a docs-only merge silently redeploys prod for nothing — **bundle the docs into the next code PR** and respect the repo's approval gate (e.g. CEO go). Do not merge autonomously.
4. **Demote the vault to a re-exported mirror**: SoT is now repo `.claude/` + the graph; the workbench vault is regenerated (graphify artifacts + export), never hand-maintained in parallel — note this in the vault index.
5. Write the **next-session handoff** into `<MEMORY_DIR>` (what shipped, what's pending, the merge boundary state).

## Gotchas (hard-won)

| Gotcha | Mitigation |
|--------|------------|
| graphify full corpus ingests `.md` → stale-doc bleed INTO the graph | always filter to code for the structure SoT (Phase 1) |
| `file_type=="code"` alone is not enough — json/sh/test nodes carry it too | also filter by path (`.py`, exclude tests/scratch) |
| `graphify .` first-build needs an LLM key; `cluster-only` needs the `<dir>/graphify-out/graph.json` layout | use `graphify update` (AST-only) + write the canonical layout (Phase 1 snippet) |
| graph.json edge key is `links` (networkx), not `edges` | the Phase 1 snippet handles both |
| Vault-relative cites (`intent/...`) dangle when ported into the repo | repoint to repo-relative paths on port |
| `[[wikilinks]]` break GitHub/markdown link gates | convert to standard `[text](path)` links on port |
| Restructuring a rules file shifts line numbers → `.md:NN` anchors rot instantly | cite **section names**, not line numbers, for cross-doc refs |
| Why ≠ structure — decisions/incidents aren't in the call graph | harvest Why into `intent/` BEFORE deleting old docs; "none lost" |
| TOML `[[tool...]]` tables look like wikilinks to naive gates | reword or whitelist TOML array-of-tables syntax |
| Docs-only merge can silently redeploy prod (no CI path filter) | Phase 7 boundary check; bundle docs into a code PR |
| Author can't self-detect own P0s | Phase 5 dual adversarial review is mandatory, not optional |

## Verification checklist

- [ ] Phase 0 audits ran parallel + produced an explicit `disciplined`/`patchwork` verdict (didn't assume rot).
- [ ] `graphify query` on the filtered graph returns product classes, not test fixtures.
- [ ] Every `intent/` entry cites a source; no invented rationale; `(why not documented)` where unknown.
- [ ] Every topic doc was written after READING the source the graph surfaced (not from memory).
- [ ] Governance = ONE canonical page; all others cite it once, none restate.
- [ ] No hand-written per-module structure wikis remain; dangling-ref sweep clean (the Phase 4 `rg` sweep → 0 live hits).
- [ ] Dual adversarial review returned APPROVE from BOTH, zero new findings, after P0/P1 fixes.
- [ ] `<REF_GUARD>` DOC_ROOTS repointed + wired into `<LOCAL_GATE>`; `graphify hook status` = installed.
- [ ] `<LOCAL_GATE>` EXIT 0; committed on a docs branch; deploy boundary checked (no autonomous docs-only merge).
- [ ] Vault demoted to mirror; handoff memory written.
- [ ] No "100/100"/"완벽"/"최종" in any self-assessment — state residual risk + what's unverified.

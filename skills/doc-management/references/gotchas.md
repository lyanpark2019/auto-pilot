# doc-management gotchas (hard-won — read BEFORE running any mode)

Every row is a real incident, not a hypothetical. Source of truth for this table —
SKILL.md only points here; do not duplicate rows back into it.

| Gotcha | Mitigation |
|--------|------------|
| graphify full corpus ingests `.md` → stale docs bleed INTO the graph | always filter to code-only for the structure SoT (REBUILD Phase 1 snippet) |
| `file_type=="code"` alone insufficient — json/sh/test nodes carry it too | also filter by language extension + exclude tests/scratch paths |
| graph.json edge key is `links` (networkx), not `edges` | filter snippet handles both |
| `graphify .` first-build needs an LLM key; `cluster-only` needs `<dir>/graphify-out/graph.json` layout | use `graphify update` (AST-only, key-free) + write the canonical layout |
| Hard-coding the filtered graph under `/tmp` | repo-rooted `.graphify/code-only/` — survives reboots, MAINTAIN diffs against it later; gitignore it |
| Vault-relative cites (`intent/...`) and `[[wikilinks]]` dangle when ported into the repo | repoint to repo-relative paths; convert to standard `[text](path)` links |
| Line-number cites rot the moment a file is restructured | symbol anchors (`` `file.py` → `SYMBOL` ``) for churn-prone files; section names for `.md`→`.md` |
| Why ≠ structure — decisions/incidents are NOT in the call graph | harvest Why into `intent/` BEFORE deleting old docs ("none lost" invariant) |
| Moving a machine-read doc breaks the gate that parses it | discover `<MACHINE_READ_DOCS>` first; those files never move (live exception) |
| Archiving an ops-essential doc leaves an ops gap window | verify-restore at the original path in the SAME commit |
| Docs-only merge on a no-path-filter CI silently redeploys prod | check deploy governance; bundle docs into a code PR |
| Author cannot self-detect own P0s | dual adversarial review is mandatory, not self-servable |
| Global find-replace on a retired term rewrites correct history | read code per occurrence — some mentions are correct-historical |
| Grep alone cannot tell stale from historical | the auditor must READ the code at each occurrence |
| A claim looks verified because another doc asserts it | verify against code > tests > CLI > config — never against docs |
| Full-auto LLM rewrite + auto-commit | FORBIDDEN in every mode — unreviewed prose is how rot reproduces |
| Hand-maintained verification JSON (claim ledger) rots like any hand-maintained doc | retired pattern — SHA freshness (L3) + AUDIT replace it |

---
description: "Run drift detector on any project. Cross-references code AST ↔ existing docs. Finds 4 drift types: gap (undocumented), orphan (dead refs), symbol drift, claim drift (signature mismatch). Read-only — produces report, no mutations."
argument-hint: "<project_path> [--vault <vault_path>]"
allowed-tools: [Bash, Read]
---

# /vault-drift

Code ↔ docs drift report. Read-only diagnosis.

## Usage

```
/vault-drift <repo-path>                      # default: scan repo + repo/docs/
/vault-drift <repo-path> --doc-root <path>    # docs live elsewhere (e.g. separate vault)
/vault-drift <repo-path> --format json        # machine-readable
/vault-drift <repo-path> --out drift.md       # write to file
```

## What it detects

| Type | Description | Source |
|---|---|---|
| **Gap** | code module with public surface but no doc reference | `scan_code.public_classes/functions` vs no doc frontmatter `source_files` / wikilink / code_ref pointing to it |
| **Orphan** | doc references file that no longer exists on disk | `scan_docs.code_refs` not in filesystem |
| **Symbol drift** | doc backtick-mentions a symbol absent from claimed source files | doc `symbol_mentions` ∉ scanned `public_classes ∪ public_functions` |
| **Claim drift** | doc-rendered signature differs from current code | doc `name(args)` vs `scan_code.signatures[name]` |

Manual-edit pages (`frontmatter.manual_edit: true` or `<!-- manual -->` marker) excluded from drift checks — these are not auto-managed.

## Implementation

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/pipeline/drift.py" "$REPO" [--doc-root D] [--format json|md] [--out PATH]
```

## Validated

ga4-collector (103 modules, 23 docs):
- 8 gap (retention.py, anomaly/_extraction.py, adsense/services/*)
- 24 orphan (docs/ARCHITECTURE.md → collector.py/analyzer.py/reporter.py/notifier.py — renamed in refactor)
- 0 symbol drift (tight filter)
- 11 claim drift (e.g. `register(cli)` doc vs `register(cli_group: click.Group)` code)

## Next step

`/vault-drift` produces a report. To auto-fix:
```
/vault-build --source code <vault> --resume
# PM dispatches gap-filler / orphan-pruner / drift-fixer workers per drift type
```

(PM wiring to drift report is Phase 5 work; current `/vault-drift` is read-only diagnostic.)

## Limitations

- Python-only AST scan (TS/JS via tree-sitter TBD)
- Symbol drift requires docs to declare `source_files:` frontmatter
- Claim drift heuristic: backtick `name(args)` patterns only — no full markdown parser

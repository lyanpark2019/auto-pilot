---
type: layer
layer: {{LAYER}}
generated: {{DATE}}
sources:
  - 01-discover-w{{N}}
---

# {{LAYER_TITLE}} Layer

## Purpose

<1 paragraph. State the responsibility of this layer. Cite [[principles/01-doctrine]] principle(s) applied. Apply deletion test: would removing this layer reappear as duplicated logic in callers?>

## Modules

| Module | Interface / role | Depth reading |
|---|---|---|
| `<path/to/module>` | <one-line interface description> (`<path>:<line>`, `<path>:<line>`) | <Deep / Moderate / Shallow + 1-line justification> |
| ... | ... | ... |

## Public Interface Surface

- <CLI entry / BFF endpoint / public function> (`<path>:<line>`)
- ...

## Seams

- **<Seam name>**: <which layers meet here, DIP direction> (`<path>:<line>`)
- ...

## Deepening Backlog

1. **<Candidate name>**
   - Files: `<path>:<line>`, ...
   - Problem: <one line>
   - Solution: <one line>
   - Deletion test: <one line — what reappears if we don't deepen this>

(3–5 candidates total)

## Cross-links

- [[../index|Harness Engineering Index]]
- [[../principles/01-doctrine|Doctrine]]
- [[../friction-map|Friction Map]]
- [[<adjacent layer>]]
- [[../deepening-backlog|Deepening Backlog]]

#!/usr/bin/env python3
"""Generate kepano-style Obsidian `.base` dashboards for a vault.

Emits 4 base files under `<vault>/meta/bases/`:

- `sources.base` — all `type: source` pages, grouped by `source_kind`
- `concepts.base` — `type: concept`, multi-source filter + manual-edited view
- `entities.base` — `type: entity`, grouped by `kind`
- `manual-edited.base` — every `manual_edit: true` page, grouped by type

Idempotent. Overwrites existing files in place.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


SOURCES_BASE = """\
filters:
  and:
    - 'type == "source"'
    - file.inFolder("wikitree/sources/")
formulas:
  age_days: '(now() - file.ctime).days.round(0)'
properties:
  title:
    displayName: Title
  source_kind:
    displayName: Kind
  manual_edit:
    displayName: Manual?
  formula.age_days:
    displayName: Age (d)
views:
  - type: table
    name: All sources
    order:
      - file.name
      - title
      - source_kind
      - manual_edit
      - formula.age_days
  - type: cards
    name: By kind
    groupBy:
      property: source_kind
      direction: ASC
    order:
      - file.name
      - title
"""

CONCEPTS_BASE = """\
filters:
  and:
    - 'type == "concept"'
    - file.inFolder("wikitree/concepts/")
formulas:
  multi_src: 'if(source_count >= 2, "OK", "single")'
properties:
  name:
    displayName: Name
  source_count:
    displayName: Sources
  grounding:
    displayName: Grounding
  manual_edit:
    displayName: Manual?
  formula.multi_src:
    displayName: Multi-source
views:
  - type: table
    name: Multi-source concepts
    filters: 'source_count >= 2'
    order:
      - name
      - source_count
      - grounding
      - manual_edit
    groupBy:
      property: grounding
      direction: ASC
  - type: cards
    name: Manual-edited concepts
    filters: 'manual_edit == true'
    order:
      - name
      - source_count
"""

ENTITIES_BASE = """\
filters:
  and:
    - 'type == "entity"'
    - file.inFolder("wikitree/entities/")
properties:
  name:
    displayName: Name
  kind:
    displayName: Kind
  source_count:
    displayName: Sources
  manual_edit:
    displayName: Manual?
views:
  - type: table
    name: Entities by kind
    order:
      - name
      - kind
      - source_count
      - manual_edit
    groupBy:
      property: kind
      direction: ASC
  - type: cards
    name: Multi-source entities
    filters: 'source_count >= 2'
    order:
      - name
      - source_count
"""

MANUAL_BASE = """\
filters:
  and:
    - 'manual_edit == true'
    - file.inFolder("wikitree/")
properties:
  type:
    displayName: Type
  name:
    displayName: Name
  source_count:
    displayName: Sources
views:
  - type: table
    name: Manual-edited pages
    order:
      - file.name
      - type
      - name
      - source_count
    groupBy:
      property: type
      direction: ASC
"""


BASES = {
    "sources.base": SOURCES_BASE,
    "concepts.base": CONCEPTS_BASE,
    "entities.base": ENTITIES_BASE,
    "manual-edited.base": MANUAL_BASE,
}


def generate_bases(vault: Path) -> list[Path]:
    """Provide the public generate bases API."""
    vault = vault.expanduser().resolve()
    out_dir = vault / "meta" / "bases"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name, body in BASES.items():
        path = out_dir / name
        path.write_text(body, encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str]) -> int:
    """Run the bases command-line entry point."""
    parser = argparse.ArgumentParser(prog="bases")
    parser.add_argument("vault", type=Path)
    args = parser.parse_args(argv[1:])
    vault = args.vault.expanduser().resolve()
    if not (vault / "wikitree").exists():
        sys.stderr.write(f"[bases] missing {vault}/wikitree\n")
        return 2
    for path in generate_bases(vault):
        sys.stdout.write(f"[bases] wrote {path}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

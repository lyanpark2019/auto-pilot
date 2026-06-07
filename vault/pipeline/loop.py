#!/usr/bin/env python3
# ruff: noqa: E402
"""PM loop driver.

Pure orchestration — no source-specific logic. Reads adapter, runs phases:
    discover → classify → bootstrap → materialize → score → PM loop until pass

Phase 5 (PM loop) is interactive: the actual Agent dispatch happens inside Claude
Code via the vault-pm-orchestrator agent. This script prepares the plan + state.

Usage as CLI:
    python3 -m vault_builder.pipeline.loop <vault> --source notebooklm [--input <path>]
    python3 -m vault_builder.pipeline.loop <vault> --source code [--input <path>]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from sources import _adapter
from pipeline import state as pipeline_state


def run(vault: Path, source: str, input_path: Path | None = None, **opts) -> dict:
    _adapter._autodiscover()
    AdapterCls = _adapter.get(source)
    adapter = AdapterCls()

    input_path = (input_path or vault).expanduser().resolve()
    vault = vault.expanduser().resolve()

    st = pipeline_state.load(vault)
    st["source_adapter"] = source
    st.setdefault("phases", {})

    print(f"Phase 1: discover ({source})")
    items = adapter.discover(input_path, **opts)
    print(f"  → {len(items)} items")
    st["phases"]["discover"] = {"items": len(items)}

    print("Phase 1.5: classify")
    buckets = adapter.classify(items, **opts)
    print(f"  → {len(buckets)} buckets: {list(buckets)}")
    st["phases"]["classify"] = {"buckets": {c: len(v) for c, v in buckets.items()}}

    print("Phase 2: bootstrap")
    adapter.bootstrap(vault, buckets, **opts)
    st["phases"]["bootstrap"] = {"completed": True}

    print("Phase 3: materialize")
    adapter.materialize(vault, buckets, **opts)
    st["phases"]["materialize"] = {"completed": True}

    pipeline_state.save(vault, st)
    print(f"Saved state: {pipeline_state.state_path(vault)}")
    print(f"\nNext: invoke vault-pm-orchestrator agent to run PM loop. Or call /vault-score {vault} to score current state.")
    return st


def _extra_to_kwargs(extra: list[str]) -> dict:
    """Parse leftover argv into kwargs: --foo bar → {foo: 'bar'}; --flag → {flag: True}."""
    out: dict = {}
    i = 0
    while i < len(extra):
        tok = extra[i]
        if tok.startswith("--"):
            key = tok[2:].replace("-", "_")
            if i + 1 < len(extra) and not extra[i + 1].startswith("--"):
                out[key] = extra[i + 1]
                i += 2
            else:
                out[key] = True
                i += 1
        else:
            i += 1
    return out


def main() -> int:
    _adapter._autodiscover()
    available = sorted(_adapter.REGISTRY.keys()) or ["notebooklm", "code"]
    ap = argparse.ArgumentParser()
    ap.add_argument("vault", type=Path)
    ap.add_argument("--source", required=True, choices=available)
    ap.add_argument("--input", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true", help="Stop after Phase 1.5 (classify)")
    args, extra = ap.parse_known_args()
    extra_kwargs = _extra_to_kwargs(extra)

    if args.dry_run:
        adapter = _adapter.get(args.source)()
        items = adapter.discover((args.input or args.vault).expanduser().resolve(), **extra_kwargs)
        buckets = adapter.classify(items, **extra_kwargs)
        print(json.dumps({c: len(v) for c, v in buckets.items()}, indent=2))
        return 0

    run(args.vault, args.source, args.input, **extra_kwargs)
    return 0


if __name__ == "__main__":
    sys.exit(main())

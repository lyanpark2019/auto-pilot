#!/usr/bin/env python3
"""Source adapter interface.

Each input type (code / NotebookLM / api-kb / pdf / youtube / slack) implements
this protocol. The adapter handles: discover sources → classify → bootstrap vault
structure → emit ticket plan for PM loop.

Adapters live under sources/. Register in REGISTRY at bottom for dispatch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class SourceItem:
    """A single source unit to process (a notebook, a code module, an endpoint set, etc)."""

    id: str
    label: str
    kind: str                 # adapter-defined: "notebook", "module", "endpoint", ...
    category: str             # bucket assignment
    payload: dict[str, Any]   # adapter-specific blob (paths, metadata, raw text refs)


@dataclass
class TicketPlanEntry:
    """One PM ticket the adapter wants issued for this source item."""

    worker_type: str
    contract: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)    # ticket ids


class SourceAdapter(Protocol):
    """Protocol every source adapter must implement."""

    name: str                       # e.g. "notebooklm", "code", "api_kb"
    default_rubric: str             # filename in rubrics/, e.g. "notebooklm.yaml"

    def discover(self, input_path: Path, **opts: Any) -> list[SourceItem]:
        """Phase 1: list every source unit. No vault mutation yet."""
        ...

    def classify(self, items: list[SourceItem], **opts: Any) -> dict[str, list[SourceItem]]:
        """Phase 1.5: bucket items into categories. Return {cat_name: [items]}."""
        ...

    def bootstrap(self, vault: Path, buckets: dict[str, list[SourceItem]], **opts: Any) -> None:
        """Phase 2: create vault directory tree + index/log/hot/overview per cat. Idempotent."""
        ...

    def materialize(self, vault: Path, buckets: dict[str, list[SourceItem]], **opts: Any) -> None:
        """Phase 3: download/extract source text into <vault>/<cat>/raw/*.md. Idempotent."""
        ...

    def plan_tickets(self, vault: Path, round_num: int, score_state: dict[str, Any], **opts: Any) -> list[TicketPlanEntry]:
        """Phase 5+: read current score, plan tickets for next PM round."""
        ...


AdapterClass = type[SourceAdapter]
REGISTRY: dict[str, AdapterClass] = {}


def register(adapter_cls: AdapterClass) -> AdapterClass:
    """Class decorator: register adapter under its `name` attribute."""
    REGISTRY[adapter_cls.name] = adapter_cls
    return adapter_cls


def get(name: str) -> AdapterClass:
    if name not in REGISTRY:
        raise ValueError(f"unknown source adapter: {name}. registered: {list(REGISTRY)}")
    return REGISTRY[name]


def _autodiscover() -> None:
    """Import every sibling module so they register themselves."""
    import importlib
    import pkgutil
    pkg_path = Path(__file__).parent
    for mod_info in pkgutil.iter_modules([str(pkg_path)]):
        if mod_info.name.startswith("_"):
            continue
        importlib.import_module(f"sources.{mod_info.name}")


# Triggered when this module is imported via `from sources import _adapter; _adapter._autodiscover()`

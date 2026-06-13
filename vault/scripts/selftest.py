#!/usr/bin/env python3
"""Vault-subsystem self-test: validate manifest, vault agents frontmatter, scripts syntax, rubric, hooks.

The vault subsystem lives at <plugin_root>/vault/ inside the auto-pilot plugin:
- vault-internal assets (pipeline/, scripts/, sources/, rubrics/, templates/) anchor to VAULT_ROOT
- plugin-level assets (.claude-plugin/, agents/, commands/, hooks/, .mcp.json) anchor to PLUGIN_ROOT
  but agent/command frontmatter checks are scoped to the vault-owned file set —
  whole-plugin structural validation belongs to plugin-dev:plugin-validator.

Usage:
    python3 vault/scripts/selftest.py

Exit code:
    0 — all checks passed
    1 — one or more checks failed (details printed)
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, TextIO

import yaml

VAULT_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = VAULT_ROOT.parent

# The agent/command files the vault subsystem owns inside the merged plugin.
VAULT_AGENTS = frozenset({
    "vault-edge-curator", "vault-graph-enricher", "vault-knowledge-author",
    "vault-structure-curator", "vault-pm-orchestrator",
})
VAULT_COMMANDS = frozenset({
    "vault-build", "vault-score", "vault-dashboard", "vault-selftest",
})


def _write_line(stream: TextIO, message: str = "") -> None:
    stream.write(f"{message}\n")


def _emit(message: str = "") -> None:
    _write_line(sys.stdout, message)


class Check:
    """Represent Check data for this module."""
    def __init__(self, name: str):
        self.name = name
        self.failures: list[str] = []

    def fail(self, msg: str) -> None:
        self.failures.append(msg)

    def ok(self) -> bool:
        return not self.failures


def _check_manifest() -> Check:
    c = Check("manifest")
    p = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
    if not p.exists():
        c.fail(f"missing: {p}")
        return c
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        c.fail(f"invalid JSON: {e}")
        return c
    for k in ("name", "version", "description"):
        if k not in data:
            c.fail(f"plugin.json missing field: {k}")
    if not re.match(r"^\d+\.\d+\.\d+", str(data.get("version", ""))):
        c.fail(f"version not semver: {data.get('version')}")
    return c


def _check_marketplace() -> Check:
    """Validate against the official claude-code marketplace.schema.json shape.

    Required top-level: name, description, owner, plugins[]
    Per-plugin required: name, description, source
    """
    c = Check("marketplace")
    p = PLUGIN_ROOT / ".claude-plugin" / "marketplace.json"
    if not p.exists():
        c.fail(f"missing: {p}")
        return c
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        c.fail(f"invalid JSON: {e}")
        return c
    for k in ("name", "description", "owner", "plugins"):
        if k not in data:
            c.fail(f"marketplace.json missing top-level field: {k}")
    plugins = data.get("plugins")
    if isinstance(plugins, list):
        for i, pl in enumerate(plugins):
            for k in ("name", "description", "source"):
                if k not in pl:
                    c.fail(f"marketplace.json plugins[{i}] missing field: {k}")
    return c


ALLOWED_MODELS = {"opus", "sonnet", "haiku", "inherit"}
FM_PATTERN = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def _agent_files(agents_dir: Path) -> list[Path]:
    return [
        f for f in agents_dir.glob("*.md")
        if not f.name.startswith("_") and f.stem in VAULT_AGENTS
    ]


def _all_agent_files(agents_dir: Path) -> list[Path]:
    return sorted(f for f in agents_dir.glob("*.md") if not f.name.startswith("_"))


def _agent_frontmatter(path: Path, c: Check) -> dict[str, Any] | None:
    m = FM_PATTERN.match(path.read_text())
    if not m:
        c.fail(f"{path.name}: missing frontmatter")
        return None
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        c.fail(f"{path.name}: invalid YAML frontmatter: {e}")
        return None
    if not isinstance(fm, dict):
        c.fail(f"{path.name}: frontmatter not a dict")
        return None
    return fm


def _validate_agent_frontmatter(path: Path, fm: dict[str, Any], c: Check) -> None:
    for k in ("name", "description"):
        if k not in fm:
            c.fail(f"{path.name}: missing field '{k}'")
    if fm.get("name") and fm["name"] != path.stem:
        c.fail(f"{path.name}: name '{fm['name']}' != stem '{path.stem}'")
    tools = fm.get("tools")
    if tools is not None and not isinstance(tools, (str, list)):
        c.fail(f"{path.name}: tools must be CSV string or list")
    model = fm.get("model")
    if model is not None and model not in ALLOWED_MODELS:
        c.fail(f"{path.name}: model '{model}' not in {ALLOWED_MODELS}")


def _check_agents() -> Check:
    c = Check("agents")
    agents_dir = PLUGIN_ROOT / "agents"
    if not agents_dir.exists():
        c.fail("agents/ missing")
        return c
    agent_files = _agent_files(agents_dir)
    missing = VAULT_AGENTS - {f.stem for f in agent_files}
    if missing:
        c.fail(f"vault agents missing from agents/: {sorted(missing)}")
    if len(agent_files) < len(VAULT_AGENTS):
        c.fail(f"only {len(agent_files)} vault agents found (expected {len(VAULT_AGENTS)}: {sorted(VAULT_AGENTS)})")
    for f in _all_agent_files(agents_dir):
        fm = _agent_frontmatter(f, c)
        if fm is not None:
            _validate_agent_frontmatter(f, fm, c)
    return c


def _check_scripts() -> Check:
    c = Check("scripts")
    scripts_dir = VAULT_ROOT / "scripts"
    for f in scripts_dir.glob("*.py"):
        try:
            ast.parse(f.read_text())
        except SyntaxError as e:
            c.fail(f"{f.name}: syntax error line {e.lineno}: {e.msg}")
    return c


def _check_rubric() -> Check:
    c = Check("rubric")
    p = VAULT_ROOT / "templates" / "rubric.yaml"
    if not p.exists():
        c.fail(f"missing: {p}")
        return c
    try:
        data = yaml.safe_load(p.read_text())
    except yaml.YAMLError as e:
        c.fail(f"invalid YAML: {e}")
        return c
    if not isinstance(data, dict):
        c.fail("rubric not a dict")
        return c
    for k in ("structural", "content"):
        if k not in data:
            c.fail(f"rubric missing section: {k}")
            continue
        if not isinstance(data[k], dict) or "dimensions" not in data[k]:
            c.fail(f"rubric.{k} missing 'dimensions'")
            continue
        # Verify every dim has a 'max' field — required for score script
        for dim_name, dim_cfg in (data[k].get("dimensions") or {}).items():
            if not isinstance(dim_cfg, dict):
                c.fail(f"rubric.{k}.{dim_name} not a dict")
                continue
            if "max" not in dim_cfg:
                c.fail(f"rubric.{k}.{dim_name} missing 'max' field")
    # cost.mode must be one of allowed values
    cost = data.get("cost") or {}
    if "mode" in cost and cost["mode"] not in ("subscription", "api"):
        c.fail(f"rubric.cost.mode must be 'subscription' or 'api', got '{cost['mode']}'")
    return c


def _check_hooks() -> Check:
    c = Check("hooks")
    p = PLUGIN_ROOT / "hooks" / "hooks.json"
    if not p.exists():
        return c  # optional
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        c.fail(f"invalid JSON: {e}")
        return c
    hooks_section = data.get("hooks", {})
    for event, entries in hooks_section.items():
        if not isinstance(entries, list):
            c.fail(f"hooks.{event} not a list")
            continue
        for i, entry in enumerate(entries):
            for hook in entry.get("hooks", []):
                cmd = hook.get("command", "")
                if cmd.startswith("${CLAUDE_PLUGIN_ROOT}/"):
                    rel = cmd.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].split()[0]
                    target = PLUGIN_ROOT / rel
                    if not target.exists():
                        c.fail(f"hooks.{event}[{i}] command missing: {target}")
                    elif not os.access(target, os.X_OK):
                        c.fail(f"hooks.{event}[{i}] not executable: {target}")
    return c


def _check_mcp() -> Check:
    c = Check("mcp")
    p = PLUGIN_ROOT / ".mcp.json"
    if not p.exists():
        return c
    try:
        data = json.loads(p.read_text())
    except json.JSONDecodeError as e:
        c.fail(f"invalid JSON: {e}")
        return c
    servers = data.get("mcpServers", {})
    for name, cfg in servers.items():
        cmd = cfg.get("command")
        if not cmd:
            c.fail(f"mcp server {name}: missing command")
        args = cfg.get("args", [])
        for a in args:
            if isinstance(a, str) and a.startswith("${CLAUDE_PLUGIN_ROOT}/"):
                rel = a.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1]
                if not (PLUGIN_ROOT / rel).exists():
                    c.fail(f"mcp server {name}: arg path missing: {rel}")
    return c


def _check_commands() -> Check:
    c = Check("commands")
    cmds_dir = PLUGIN_ROOT / "commands"
    if not cmds_dir.exists():
        c.fail("commands/ missing")
        return c
    missing = VAULT_COMMANDS - {f.stem for f in cmds_dir.glob("*.md")}
    if missing:
        c.fail(f"vault commands missing from commands/: {sorted(missing)}")
    fm_pattern = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
    for f in cmds_dir.glob("*.md"):
        if f.stem not in VAULT_COMMANDS:
            continue
        text = f.read_text()
        m = fm_pattern.match(text)
        if not m:
            c.fail(f"{f.name}: missing frontmatter")
            continue
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError as e:
            c.fail(f"{f.name}: invalid YAML: {e}")
            continue
        # `name:` is NOT a spec field for commands (filename is the name).
        # Only `description` is required per command-development spec.
        if "description" not in fm:
            c.fail(f"{f.name}: missing description")
    return c


def _check_sources() -> Check:
    c = Check("sources")
    src_dir = VAULT_ROOT / "sources"
    if not src_dir.exists():
        c.fail("sources/ missing")
        return c
    if not (src_dir / "_adapter.py").exists():
        c.fail("sources/_adapter.py missing (adapter protocol)")
    # Verify adapter modules importable
    import sys
    sys.path.insert(0, str(VAULT_ROOT))
    try:
        from sources import _adapter
        _adapter._autodiscover()
        for required in ("notebooklm", "code"):
            if required not in _adapter.REGISTRY:
                c.fail(f"adapter not registered: {required}")
    except (ImportError, AttributeError, OSError, RuntimeError) as e:
        c.fail(f"adapter autodiscover failed: {e}")
    return c


def _check_rubrics_library() -> Check:
    c = Check("rubrics_library")
    rdir = VAULT_ROOT / "rubrics"
    if not rdir.exists():
        c.fail("rubrics/ missing")
        return c
    for required in ("notebooklm.yaml", "code-docs.yaml"):
        if not (rdir / required).exists():
            c.fail(f"rubrics/{required} missing")
    return c


def _check_restructure() -> Check:
    c = Check("restructure")
    rdir = VAULT_ROOT / "scripts" / "restructure_phases"
    if not rdir.is_dir():
        c.fail("scripts/restructure_phases/ missing")
        return c
    required = ["__init__.py", "_base.py", "_state.py", "_mapping.py",
                "phase01_backup.py", "phase02_rename.py", "phase03_sportic365_merge.py",
                "phase04_notebooklm_split.py", "phase05_skeletons.py",
                "phase06_vault_build.py", "phase07_notebooklm_create.py",
                "phase08_cleanup.py"]
    for f in required:
        if not (rdir / f).exists():
            c.fail(f"restructure_phases/{f} missing")
    loop_script = VAULT_ROOT / "scripts" / "restructure_loop.py"
    if not loop_script.exists():
        c.fail("scripts/restructure_loop.py missing")
    # vault-restructure was absorbed into vault-build --restructure (consolidation 2026-06-06)
    cmd = PLUGIN_ROOT / "commands" / "vault-build.md"
    if not cmd.exists():
        c.fail("commands/vault-build.md missing (must contain --restructure mode)")
    elif "--restructure" not in cmd.read_text():
        c.fail("commands/vault-build.md missing --restructure mode (absorb from vault-restructure)")
    return c


def run_all() -> tuple[int, list[Check]]:
    """Run run all workflow."""
    checks = [
        _check_manifest(),
        _check_marketplace(),
        _check_agents(),
        _check_scripts(),
        _check_rubric(),
        _check_hooks(),
        _check_mcp(),
        _check_commands(),
        _check_sources(),
        _check_rubrics_library(),
        _check_restructure(),
    ]
    fails = sum(1 for c in checks if not c.ok())
    return fails, checks


def main(argv: list[str]) -> int:
    """Run the selftest command-line entry point."""
    n_fail, checks = run_all()
    for c in checks:
        if c.ok():
            _emit(f"[PASS] {c.name}")
        else:
            _emit(f"[FAIL] {c.name}")
            for f in c.failures:
                _emit(f"       - {f}")
    _emit()
    if n_fail:
        _emit(f"FAILED: {n_fail}/{len(checks)} checks")
        return 1
    _emit(f"PASSED: {len(checks)}/{len(checks)} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

#!/usr/bin/env python3
"""Self-test for verifier-tier-gate.sh."""
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "verifier-tier-gate.sh")


def run_case(label: str, subagent_type: str | None, model: str | None,
             expect: str, raw_stdin: str | None = None) -> bool:
    tool_input: dict[str, object] = {"prompt": "x", "description": "x"}
    if subagent_type is not None:
        tool_input["subagent_type"] = subagent_type
    if model is not None:
        tool_input["model"] = model
    payload = raw_stdin if raw_stdin is not None else json.dumps(
        {"tool_name": "Task", "tool_input": tool_input})
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).resolve().parent.parent)
    result = subprocess.run(["bash", HOOK], input=payload,
                            capture_output=True, text=True, env=env)
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and '"deny"' in stdout) else "ALLOW"
    ok = actual == expect and result.returncode == 0
    print(f"[{'OK  ' if ok else 'FAIL'}] {label:52s} expect={expect:5s} got={actual:5s}")
    if not ok:
        print(f"       rc={result.returncode} stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


CASES: list[tuple[str, str | None, str | None, str]] = [
    ("verifier + haiku override", "auto-pilot-claude-reviewer", "haiku", "DENY"),
    ("verifier + sonnet override", "swarm-verifier", "sonnet", "DENY"),
    ("verifier + opus override (at tier)", "auto-pilot-codex-reviewer", "opus", "ALLOW"),
    ("verifier + fable override (above tier)", "review-gatekeeper", "fable", "ALLOW"),
    ("plugin-prefixed verifier + haiku", "auto-pilot:tech-critic-lead", "haiku", "DENY"),
    ("non-verifier + haiku", "auto-pilot-worker", "haiku", "ALLOW"),
    ("verifier, no model override", "auto-pilot-claude-reviewer", None, "ALLOW"),
    ("verifier + unknown model token", "swarm-verifier", "gpt-5.5", "ALLOW"),
    ("whitespace strip: ' swarm-verifier ' + ' haiku '", " swarm-verifier ", " haiku ", "DENY"),
]


def _make_payload(subagent_type: str, model: str) -> str:
    tool_input: dict[str, object] = {
        "prompt": "x",
        "description": "x",
        "subagent_type": subagent_type,
        "model": model,
    }
    return json.dumps({"tool_name": "Task", "tool_input": tool_input})


def run_concurrency_case() -> bool:
    """8 simultaneous hook invocations must ALL return deny (rc=0)."""
    label = "concurrency: 8 parallel swarm-verifier+haiku invocations"
    payload = _make_payload("swarm-verifier", "haiku")
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).resolve().parent.parent)
    procs: list[subprocess.Popen[str]] = [
        subprocess.Popen(
            ["bash", HOOK],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        for _ in range(8)
    ]
    outcomes: list[bool] = []
    for proc in procs:
        stdout, _stderr = proc.communicate(input=payload)
        is_deny = '"deny"' in stdout
        rc_ok = proc.returncode == 0
        outcomes.append(is_deny and rc_ok)
    all_ok = all(outcomes)
    deny_count = sum(outcomes)
    print(
        f"[{'OK  ' if all_ok else 'FAIL'}] {label:52s} "
        f"expect=DENY*8 got=DENY*{deny_count}"
    )
    if not all_ok:
        print(f"       individual outcomes={outcomes}")
    return all_ok


def run_temp_hygiene_case() -> bool:
    """No vtg_* temp files must remain in TMPDIR after hook exit; must also DENY."""
    label = "temp hygiene: no vtg_* files remain after run"
    with tempfile.TemporaryDirectory() as tmpdir:
        payload = _make_payload("auto-pilot-claude-reviewer", "haiku")
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).resolve().parent.parent)
        env["TMPDIR"] = tmpdir
        result = subprocess.run(
            ["bash", HOOK],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
        )
        leftover = glob.glob(os.path.join(tmpdir, "vtg_*"))
    stdout = result.stdout.strip()
    is_deny = stdout and '"deny"' in stdout
    no_leftovers = len(leftover) == 0
    ok = bool(is_deny) and no_leftovers and result.returncode == 0
    print(
        f"[{'OK  ' if ok else 'FAIL'}] {label:52s} "
        f"expect=DENY+0 leftover got={'DENY' if is_deny else 'ALLOW'}+{len(leftover)}"
    )
    if not ok:
        print(f"       rc={result.returncode} stdout={stdout!r} stderr={result.stderr.strip()!r}")
        if not no_leftovers:
            print(f"       leftover files: {leftover}")
    return ok


def run_big_payload_case() -> bool:
    """512KiB filler in tool_input.prompt must not crash stdin path; must DENY."""
    label = "big payload (512KiB prompt field): swarm-verifier+haiku"
    tool_input: dict[str, object] = {
        "prompt": "A" * (512 * 1024),
        "description": "x",
        "subagent_type": "swarm-verifier",
        "model": "haiku",
    }
    payload = json.dumps({"tool_name": "Task", "tool_input": tool_input})
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).resolve().parent.parent)
    result = subprocess.run(
        ["bash", HOOK],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
    )
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and '"deny"' in stdout) else "ALLOW"
    ok = actual == "DENY" and result.returncode == 0
    print(
        f"[{'OK  ' if ok else 'FAIL'}] {label:52s} expect=DENY  got={actual:5s}"
    )
    if not ok:
        print(f"       rc={result.returncode} stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


def run_deny_json_valid_case() -> bool:
    """Deny output must be parseable JSON (escaping correctness check)."""
    label = "deny JSON valid: haiku override emits parseable JSON"
    payload = _make_payload("auto-pilot-claude-reviewer", "haiku")
    env = os.environ.copy()
    env["CLAUDE_PLUGIN_ROOT"] = str(Path(__file__).resolve().parent.parent)
    result = subprocess.run(["bash", HOOK], input=payload,
                            capture_output=True, text=True, env=env)
    stdout = result.stdout.strip()
    ok = False
    try:
        parsed = json.loads(stdout)
        ok = (
            result.returncode == 0
            and parsed.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        )
    except (json.JSONDecodeError, AttributeError):
        pass
    print(
        f"[{'OK  ' if ok else 'FAIL'}] {label:52s} "
        f"expect=DENY+valid-JSON got={'valid-JSON' if ok else 'invalid/ALLOW'}"
    )
    if not ok:
        print(f"       rc={result.returncode} stdout={stdout!r}")
    return ok


def _make_temp_root(
    tmpdir: str,
    *,
    include_verifier_agents: bool = True,
    extra_verifier_agents: list[str] | None = None,
    verifier_min_tier: str = "opus",
) -> str:
    """Build a minimal plugin root under tmpdir for yaml-driven tests."""
    import shutil

    root = os.path.join(tmpdir, "root")
    scripts_dir = os.path.join(root, "scripts")
    yaml_dir = os.path.join(root, "skills", "auto-pilot", "references")
    os.makedirs(scripts_dir, exist_ok=True)
    os.makedirs(yaml_dir, exist_ok=True)

    # Copy real _routing.py so the embedded Python can import it.
    real_routing = str(Path(__file__).resolve().parent.parent / "scripts" / "_routing.py")
    shutil.copy(real_routing, os.path.join(scripts_dir, "_routing.py"))

    yaml_parts = [
        "schema_version: 1",
        "agent_model_rank:",
        "  fable: 0",
        "  opus: 1",
        "  sonnet: 3",
        "  haiku: 4",
        f"verifier_min_tier: {verifier_min_tier}",
    ]
    if include_verifier_agents:
        agents = extra_verifier_agents if extra_verifier_agents is not None else [
            "auto-pilot-codex-reviewer",
            "auto-pilot-claude-reviewer",
            "review-gatekeeper",
            "swarm-verifier",
            "tech-critic-lead",
        ]
        yaml_parts.append("verifier_agents:")
        for agent in agents:
            yaml_parts.append(f"  - {agent}")

    yaml_content = "\n".join(yaml_parts) + "\n"
    with open(os.path.join(yaml_dir, "model-routing.yaml"), "w") as f:
        f.write(yaml_content)

    return root


def run_yaml_driven_missing_key_case() -> bool:
    """yaml without verifier_agents: key -> fail-open ALLOW for a verifier+haiku."""
    label = "yaml missing verifier_agents: -> fail-open ALLOW"
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_temp_root(tmpdir, include_verifier_agents=False)
        payload = _make_payload("auto-pilot-claude-reviewer", "haiku")
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = root
        result = subprocess.run(
            ["bash", HOOK],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
        )
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and '"deny"' in stdout) else "ALLOW"
    ok = actual == "ALLOW" and result.returncode == 0
    print(
        f"[{'OK  ' if ok else 'FAIL'}] {label:52s} expect=ALLOW got={actual:5s}"
    )
    if not ok:
        print(f"       rc={result.returncode} stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


def run_yaml_driven_custom_agent_deny_case() -> bool:
    """Custom yaml with my-custom-verifier in verifier_agents + haiku -> DENY."""
    label = "yaml custom agent my-custom-verifier+haiku -> DENY"
    with tempfile.TemporaryDirectory() as tmpdir:
        root = _make_temp_root(
            tmpdir,
            extra_verifier_agents=["my-custom-verifier"],
            verifier_min_tier="opus",
        )
        payload = _make_payload("my-custom-verifier", "haiku")
        env = os.environ.copy()
        env["CLAUDE_PLUGIN_ROOT"] = root
        result = subprocess.run(
            ["bash", HOOK],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
        )
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and '"deny"' in stdout) else "ALLOW"
    ok = actual == "DENY" and result.returncode == 0
    print(
        f"[{'OK  ' if ok else 'FAIL'}] {label:52s} expect=DENY  got={actual:5s}"
    )
    if not ok:
        print(f"       rc={result.returncode} stdout={stdout!r} stderr={result.stderr.strip()!r}")
    return ok


def main() -> None:
    results = [run_case(*c) for c in CASES]
    results.append(run_case("unparseable stdin (fail-open)", None, None,
                            "ALLOW", raw_stdin="{ not json"))
    results.append(run_concurrency_case())
    results.append(run_temp_hygiene_case())
    results.append(run_big_payload_case())
    results.append(run_deny_json_valid_case())
    results.append(run_yaml_driven_missing_key_case())
    results.append(run_yaml_driven_custom_agent_deny_case())
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

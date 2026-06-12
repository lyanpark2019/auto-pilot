#!/usr/bin/env python3
"""Self-test for verifier-tier-gate.sh."""
import json
import os
import subprocess
import sys
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
]


def main() -> None:
    results = [run_case(*c) for c in CASES]
    results.append(run_case("unparseable stdin (fail-open)", None, None,
                            "ALLOW", raw_stdin="{ not json"))
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

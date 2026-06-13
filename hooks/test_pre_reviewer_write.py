#!/usr/bin/env python3
"""Test runner for pre-reviewer-write.sh hook.

Script-style: invokes the hook via subprocess to mimic the harness handing
JSON via stdin.  Matches the pattern of hooks/test_guard_destructive.py.

Tests:
  1. Malformed JSON with reviewer role → exit 2 (BLOCKED/deny)
  2. Empty object {} with reviewer role → exit 2 (BLOCKED/deny)
  3. Valid Edit inside output dir with reviewer role → exit 0 (allow)
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = str(Path(__file__).parent / "pre-reviewer-write.sh")
OUTPUT_DIR = "/tmp/ok"


def run_case(
    label: str,
    expect: str,
    payload_str: str,
    env_extra: dict[str, str] | None = None,
) -> bool:
    env = os.environ.copy()
    env["AUTO_PILOT_SUBAGENT_ROLE"] = "codex-reviewer"
    env["AUTO_PILOT_OUTPUT_DIR"] = OUTPUT_DIR
    if env_extra:
        env.update(env_extra)

    result = subprocess.run(
        ["bash", HOOK],
        input=payload_str,
        capture_output=True,
        text=True,
        env=env,
    )

    if expect == "DENY":
        actual = "DENY" if result.returncode == 2 else "ALLOW"
    else:
        actual = "ALLOW" if result.returncode == 0 else "DENY"

    pass_fail = "PASS" if actual == expect else "FAIL"
    status_icon = "OK  " if pass_fail == "PASS" else "FAIL"
    print(f"[{status_icon}] {label:45s}  expect={expect:5s}  got={actual:5s}  rc={result.returncode}")
    if pass_fail == "FAIL":
        print(f"       payload: {payload_str!r}")
        print(f"       stderr:  {result.stderr.strip()!r}")
        print(f"       stdout:  {result.stdout.strip()!r}")
    return pass_fail == "PASS"


CASES: list[tuple[str, str, str]] = [
    (
        "Malformed JSON with reviewer role → DENY",
        "DENY",
        "not json",
    ),
    (
        "Empty object {} with reviewer role → DENY",
        "DENY",
        "{}",
    ),
    (
        "Valid Edit inside output dir → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": f"{OUTPUT_DIR}/review.md"},
        }),
    ),
    # A3 fix: null tool_name must fail-closed (was bypassing via None→"None" string)
    (
        "null tool_name with Bash payload → DENY",
        "DENY",
        json.dumps({
            "tool_name": None,
            "tool_input": {"command": "rm -rf /tmp/x"},
        }),
    ),
    # DEFECT 2: Bash branch with a STRING (non-dict) tool_input previously raised
    # an uncaught AttributeError → empty cmd → grep no-match → exit 0 (mutation
    # allowed).  Must fail-closed → DENY.
    (
        "Bash string tool_input (non-dict) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": "git push origin x",
        }),
    ),
    # Control: dict tool_input with a SAFE (read-only) Bash command → ALLOW.
    (
        "Bash dict tool_input, safe read cmd → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
        }),
    ),
    # codex re-review: a non-string command (list) str()-renders to a form the
    # mutation grep never matches → must fail-closed → DENY.
    (
        "Bash list-type command (non-string) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": ["rm", "-rf", "/"]},
        }),
    ),
    # Opus r4: path-qualified git must also be caught
    (
        "Bash /usr/bin/git push (abs path) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "/usr/bin/git push origin x"},
        }),
    ),
    # Anchored-regex fixwave: unanchored `rm ` / `sed -i` previously matched
    # INSIDE words ("perform ", "parsed -i") → false-deny on harmless reads.
    (
        "Bash 'echo perform task' (rm substring) → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "echo perform task"},
        }),
    ),
    (
        "Bash 'echo parsed -i' (sed -i substring) → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "echo parsed -i"},
        }),
    ),
    # Anchoring must NOT lose path-qualified binaries or ^-anchored ones.
    (
        "Bash rm -rf (start of cmd) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /tmp/x"},
        }),
    ),
    (
        "Bash /bin/rm (path-qualified) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "/bin/rm -rf /tmp/x"},
        }),
    ),
    (
        "Bash sed -i in-place → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "sed -i '' s/a/b/ file.txt"},
        }),
    ),
    # git global-opt bypass: -C/-c flag+value pairs before the subcommand are
    # skipped, so `git -C <path> push` is still a push.
    (
        "Bash git -C path push → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git -C /repo push origin x"},
        }),
    ),
    # Non-flag token after git breaks the chain — a mutation WORD later in a
    # read-only pipeline must not deny.
    (
        "Bash git log | grep commit → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git log --oneline | grep commit"},
        }),
    ),
    # Whitespace-only file_path for Edit: case "$file_path" in "$allowed_output_dir"/*)
    # "   " does not start with "/tmp/ok/" so it is out-of-scope → DENY.
    (
        "Edit whitespace-only file_path → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "   "},
        }),
    ),
    # Tab-only file_path: same shape, still not inside allowed_output_dir → DENY.
    (
        "Edit tab-only file_path → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "\t"},
        }),
    ),
    # Whitespace-only Bash command: the mutation grep patterns all require real tokens;
    # "   " contains no mutation keyword → ALLOW.
    (
        "Bash whitespace-only command → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "   "},
        }),
    ),
    # SEC2: redirection bypass cases — previously ALLOWed, must now DENY.
    (
        "Bash echo redirect to file → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "echo x > /etc/evil"},
        }),
    ),
    (
        "Bash printf redirect → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "printf y > /tmp/out"},
        }),
    ),
    (
        "Bash cat redirect → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "cat a > b"},
        }),
    ),
    (
        "Bash perl -i in-place → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "perl -i -pe 's/a/b/' f"},
        }),
    ),
    (
        "Bash python3 -c open(w) → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": 'python3 -c \'open("f","w").write(1)\''},
        }),
    ),
    (
        "Bash ruby -e → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": 'ruby -e "x=1"'},
        }),
    ),
    (
        "Bash cp copy → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "cp /etc/passwd /tmp/leak"},
        }),
    ),
    (
        "Bash ln symlink → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "ln -s a b"},
        }),
    ),
    (
        "Bash dd → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "dd if=x of=y"},
        }),
    ),
    (
        "Bash append redirect → DENY",
        "DENY",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "echo x >> /tmp/f"},
        }),
    ),
    # SEC2: regression-ALLOW — must not over-block read-only usage.
    (
        "Bash pytest fd-dup pipe → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "pytest 2>&1 | tail"},
        }),
    ),
    (
        "Bash python3 -m pytest → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "python3 -m pytest -q"},
        }),
    ),
    (
        "Bash git diff redirect-free → ALLOW",
        "ALLOW",
        json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "git diff --name-only base..HEAD"},
        }),
    ),
]


def main() -> None:
    results = [run_case(*c) for c in CASES]
    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Test runner for gh-auth-preflight.sh hook.

Script-style: invokes the hook via subprocess with JSON on stdin. Matches the
pattern of hooks/test_pre_reviewer_write.py / hooks/test_guard_destructive.py.

Strategy — isolate the FIRST-TOKEN DETECTION layer (DEFECT 3) without a live
`gh` call:
  * A temp git repo is the cwd, with `origin` set to a lyanpark2019 URL so the
    owner resolves to `lyanpark2019` (expected_user).
  * The per-owner cache file is pre-seeded (in an isolated TMPDIR) with a WRONG
    active user ("someone-else") and a fresh mtime, so cache TTL is honoured and
    no network `gh api user` call happens.

Consequences:
  * If the hook DETECTS the segment as a gh command, it reaches owner →
    cache → mismatch → DENY. So DENY proves detection worked.
  * If the evasion SUCCEEDS (first-token check misses), the hook exits 0 early
    → ALLOW. So ALLOW proves the evasion slipped through.

Each DEFECT-3 evasion form (quoted gh, \\gh, command/builtin/exec wrapper,
absolute path) must therefore DENY. Controls: `gh auth switch` must ALLOW
(skip), a non-gh command must ALLOW.
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HOOK = str(Path(__file__).parent / "gh-auth-preflight.sh")
OWNER = "lyanpark2019"
ORIGIN = f"git@github.com:{OWNER}/auto-pilot.git"


def make_repo(tmp: str) -> None:
    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", tmp, *args],
            check=True, capture_output=True, text=True,
        )
    git("init", "-q")
    git("remote", "add", "origin", ORIGIN)


def run_case(label: str, expect: str, cmd: str, repo: str, tmpdir: str) -> bool:
    env = os.environ.copy()
    env["TMPDIR"] = tmpdir
    # Pre-seed the owner cache with a WRONG active user so a mismatch fires
    # without any live `gh` call.
    cache = Path(tmpdir) / f"gh-auth-{OWNER}.cache"
    cache.write_text("someone-else")
    now = time.time()
    os.utime(cache, (now, now))

    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd, "cwd": repo}})
    result = subprocess.run(
        ["bash", HOOK],
        input=payload, capture_output=True, text=True, env=env, cwd=repo,
    )
    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and '"permissionDecision":"deny"' in stdout) else "ALLOW"
    pass_fail = "PASS" if actual == expect else "FAIL"
    status_icon = "OK  " if pass_fail == "PASS" else "FAIL"
    print(f"[{status_icon}] {label:48s}  expect={expect:5s}  got={actual:5s}")
    if pass_fail == "FAIL":
        print(f"       cmd:    {cmd!r}")
        print(f"       stdout: {stdout!r}")
        print(f"       stderr: {result.stderr.strip()!r}")
    return pass_fail == "PASS"


CASES: list[tuple[str, str, str]] = [
    # Baseline (already worked): plain gh → detected → DENY (mismatch).
    ("plain gh pr list",                "DENY", "gh pr list"),
    ("env-prefix gh pr list",           "DENY", "GH_TOKEN=x gh pr list"),
    # DEFECT 3 evasions — must DENY (detection must see through them).
    ('double-quoted "gh" pr list',      "DENY", '"gh" pr list'),
    ("single-quoted 'gh' pr list",      "DENY", "'gh' pr list"),
    ("backslash \\gh pr list",          "DENY", "\\gh pr list"),
    ("command gh pr list",              "DENY", "command gh pr list"),
    ("builtin-wrapped exec gh pr list", "DENY", "exec gh pr list"),
    ("absolute /usr/bin/gh pr list",    "DENY", "/usr/bin/gh pr list"),
    # codex re-review: command-substitution / backtick wrappers → fail toward firing.
    ("backtick `gh` pr list",           "DENY", "`gh` pr list"),
    ("cmd-subst $(echo gh) pr list",    "DENY", "$(echo gh) pr list"),
    # $VAR indirection hardening (FIX 2): VAR=gh; "$VAR" forms must DENY.
    ("$VAR: g=gh; \"$g\" pr merge 5",  "DENY", 'g=gh; "$g" pr merge 5'),
    ("$VAR: G=gh; \"$G\" pr merge",    "DENY", 'G=gh; "$G" pr merge'),
    # Controls — must ALLOW.
    ("gh auth switch (skip)",           "ALLOW", "gh auth switch -u lyanpark2019"),
    ("gh auth status (skip)",           "ALLOW", "gh auth status"),
    ("non-gh command (git status)",     "ALLOW", "git status"),
    ("substring 'weigh' not gh",        "ALLOW", "echo weigh more"),
    ("cmd-subst no gh token",           "ALLOW", "echo $(date) more"),
    # $VAR with non-gh value must ALLOW (no false positive).
    ("$VAR: foo=bar; echo $foo (ALLOW)", "ALLOW", "foo=bar; echo $foo"),
]


def main() -> None:
    with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as tmpdir:
        make_repo(repo)
        results = [run_case(label, exp, cmd, repo, tmpdir) for label, exp, cmd in CASES]
    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Test runner for deletion-diff-guard.sh hook.

Script-style: invokes the hook via subprocess to mimic the harness handing
JSON via stdin. Mirrors the structure and type annotations of
hooks/test_branch_lock.py.

The hook denies `git push` when deletions > 500 AND deletions > 3× insertions
AND an upstream tracking ref exists.  No upstream → allow (first push).

Decision is read from the hook's JSON output: a `"permissionDecision":"deny"`
token means DENY; absence (silent exit 0) means ALLOW.

Security regression (SEC5 2026-06-13):
  A command-string prefix `AUTO_PILOT_BIG_DELETE_OK=1 git push` must NOT
  be honored — the env-prefix never reaches the hook subprocess env; accepting
  it as a bypass string would make the guard self-grantable by any subagent.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "deletion-diff-guard.sh")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def _git(repo: str, *args: str) -> None:
    env = os.environ.copy()
    env.update(GIT_ENV)
    subprocess.run(
        ["git", "-C", repo, *args],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )


def make_repo_with_upstream(tmp_dir: str) -> tuple[str, str]:
    """Create a bare origin + work repo where HEAD has ~700 deletions vs @{u}.

    Returns (work_repo_path, bare_repo_path).
    The work repo's HEAD is ~700 deletions, 0 insertions relative to @{u},
    satisfying deletions>500 and deletions>3×insertions.
    """
    bare = os.path.join(tmp_dir, "bare.git")
    work = os.path.join(tmp_dir, "work")
    os.makedirs(bare)
    os.makedirs(work)

    env = os.environ.copy()
    env.update(GIT_ENV)

    # Init bare repo
    subprocess.run(["git", "init", "--bare", "-q", bare], check=True,
                   capture_output=True, text=True, env=env)

    # Init work repo
    _git(work, "init", "-q", "-b", "main")
    _git(work, "remote", "add", "origin", f"file://{bare}")

    # Seed a file with 700 lines so upstream has content to delete
    big_file = Path(work) / "bigfile.txt"
    big_file.write_text("\n".join(f"line {i}" for i in range(700)) + "\n")
    _git(work, "add", "bigfile.txt")
    _git(work, "commit", "-q", "-m", "seed")

    # Push to establish upstream tracking ref @{u}
    _git(work, "push", "-u", "origin", "main")

    # Now delete all lines — HEAD is ~700 deletions vs @{u}
    big_file.write_text("")
    _git(work, "add", "bigfile.txt")
    _git(work, "commit", "-q", "-m", "delete all")

    return work, bare


def make_small_diff_repo(tmp_dir: str) -> str:
    """Create a work repo where HEAD adds exactly one line vs @{u}.

    Satisfies upstream present but does NOT meet the large-deletion threshold.
    """
    bare = os.path.join(tmp_dir, "bare2.git")
    work = os.path.join(tmp_dir, "work2")
    os.makedirs(bare)
    os.makedirs(work)

    env = os.environ.copy()
    env.update(GIT_ENV)

    subprocess.run(["git", "init", "--bare", "-q", bare], check=True,
                   capture_output=True, text=True, env=env)
    _git(work, "init", "-q", "-b", "main")
    _git(work, "remote", "add", "origin", f"file://{bare}")

    seed = Path(work) / "seed.txt"
    seed.write_text("hello\n")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-q", "-m", "seed")
    _git(work, "push", "-u", "origin", "main")

    # Add one line — tiny diff, well below threshold
    seed.write_text("hello\nworld\n")
    _git(work, "add", "seed.txt")
    _git(work, "commit", "-q", "-m", "add one line")

    return work


def run_case(
    label: str,
    expect: str,
    cmd: str,
    cwd: str,
    env_extra: dict[str, str] | None = None,
) -> bool:
    env = os.environ.copy()
    env.pop("AUTO_PILOT_BIG_DELETE_OK", None)
    if env_extra:
        env.update(env_extra)

    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd, "cwd": cwd}})

    result = subprocess.run(
        ["bash", HOOK],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
    )

    stdout = result.stdout.strip()
    actual = "DENY" if (stdout and '"permissionDecision":"deny"' in stdout) else "ALLOW"
    pass_fail = "PASS" if actual == expect else "FAIL"
    status_icon = "OK  " if pass_fail == "PASS" else "FAIL"
    print(f"[{status_icon}] {label:60s}  expect={expect:5s}  got={actual:5s}")
    if pass_fail == "FAIL":
        print(f"       cmd:    {cmd!r}")
        print(f"       stdout: {stdout!r}")
        print(f"       stderr: {result.stderr.strip()!r}")
    return pass_fail == "PASS"


def main() -> None:
    results: list[bool] = []

    with tempfile.TemporaryDirectory() as tmp:
        large_work, _bare = make_repo_with_upstream(tmp)
        small_work = make_small_diff_repo(tmp)

        # (a) Large-deletion push, no token → DENY
        results.append(run_case(
            "large deletion push, no token → DENY",
            "DENY",
            "git push",
            large_work,
        ))

        # (b) Large-deletion push + real env token → ALLOW
        results.append(run_case(
            "large deletion push + real env token → ALLOW",
            "ALLOW",
            "git push",
            large_work,
            env_extra={"AUTO_PILOT_BIG_DELETE_OK": "1"},
        ))

        # (c) Self-grant repro: cmd-prefix is NOT a bypass (security regression pin)
        results.append(run_case(
            "cmd-prefix self-grant (AUTO_PILOT_BIG_DELETE_OK=1 git push) → DENY",
            "DENY",
            "AUTO_PILOT_BIG_DELETE_OK=1 git push",
            large_work,
        ))

        # (d) Small-diff push → ALLOW (below threshold)
        results.append(run_case(
            "small diff push → ALLOW",
            "ALLOW",
            "git push",
            small_work,
        ))

        # (e) Non-push git command → ALLOW
        results.append(run_case(
            "git status (non-push) → ALLOW",
            "ALLOW",
            "git status",
            large_work,
        ))

        # (f) Active-run: large-deletion push + HEADLESS=1, no token → DENY
        results.append(run_case(
            "active run (HEADLESS=1) large deletion, no token → DENY",
            "DENY",
            "git push",
            large_work,
            env_extra={"AUTO_PILOT_HEADLESS": "1"},
        ))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

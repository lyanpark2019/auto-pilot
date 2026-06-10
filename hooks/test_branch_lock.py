#!/usr/bin/env python3
"""Test runner for branch-lock.sh hook.

Script-style: invokes the hook via subprocess to mimic the harness handing
JSON via stdin. Matches the pattern of hooks/test_pre_reviewer_write.py /
hooks/test_guard_destructive.py.

The hook gates `git commit` / `git push` against protected branches (main /
master). For commit it gates on the current HEAD branch; for push it gates on
the refspec DST (bare push → HEAD). A temp git repo is used as cwd so the
current-branch lookups (`git branch --show-current`) resolve.

Decision is read from the hook's JSON output: a `"permissionDecision":"deny"`
token means DENY; absence (silent exit 0) means ALLOW.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "branch-lock.sh")


def make_repo(tmp: str, branch: str) -> str:
    """Init a git repo at tmp with one commit, checked out on `branch`."""
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "t"
    env["GIT_AUTHOR_EMAIL"] = "t@t"
    env["GIT_COMMITTER_NAME"] = "t"
    env["GIT_COMMITTER_EMAIL"] = "t@t"

    def git(*args: str) -> None:
        subprocess.run(
            ["git", "-C", tmp, *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    git("init", "-q")
    # Seed one commit so branch --show-current is meaningful.
    (Path(tmp) / "seed").write_text("x\n")
    git("add", "seed")
    git("commit", "-q", "-m", "seed")
    # Rename whatever the default branch is to `main` first, then branch.
    git("branch", "-M", "main")
    if branch != "main":
        git("checkout", "-q", "-b", branch)
    return tmp


def run_case(
    label: str,
    expect: str,
    cmd: str,
    cwd: str,
    env_extra: dict[str, str] | None = None,
) -> bool:
    env = os.environ.copy()
    # Ensure no ambient bypass unless a case opts in.
    env.pop("AUTO_PILOT_MAIN_OK", None)
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
    print(f"[{status_icon}] {label:55s}  expect={expect:5s}  got={actual:5s}")
    if pass_fail == "FAIL":
        print(f"       cmd:    {cmd!r}")
        print(f"       stdout: {stdout!r}")
        print(f"       stderr: {result.stderr.strip()!r}")
    return pass_fail == "PASS"


def main() -> None:
    results: list[bool] = []
    with tempfile.TemporaryDirectory() as main_repo, \
            tempfile.TemporaryDirectory() as feat_repo:
        make_repo(main_repo, "main")
        make_repo(feat_repo, "feature/x")

        # --- DENY cases on a repo whose HEAD is main ---
        deny_main = [
            # baseline already-working
            ("bare push origin main",          "git push origin main"),
            ("push +main force",               "git push origin +main"),
            ("push HEAD",                      "git push origin HEAD"),
            ("push refs/heads/main",           "git push origin refs/heads/main"),
            ("push src:main refspec",          "git push origin feature/x:main"),
            ("multi-refspec incl main",        "git push origin foo:bar feature/x:main"),
            ("-C . push main",                 f"git -C {main_repo} push origin main"),
            ("--force-with-lease main",        "git push --force-with-lease origin main"),
            ("commit on main",                 "git commit -m x"),
            ("bare push (no refspec) on main", "git push"),
            ("push origin (remote only) main", "git push origin"),
            # NEW bypass repros — must DENY
            ("subshell (push origin main)",    "(git push origin main)"),
            ('double-quoted "main"',           'git push origin "main"'),
            ("single-quoted 'main'",           "git push origin 'main'"),
            ("brace group { push main; }",     "{ git push origin main; }"),
            # shlex ValueError fail-closed: unbalanced quote → __CURRENT__ →
            # gates HEAD (main here).  Exercises the _mentions fallback path.
            ('unbalanced quote push "main',    'git push origin "main'),
            # Multiline + unbalanced quote: _mentions needs re.S to see the
            # push word across the newline (would fail-open without it).
            ("multiline unbalanced quote",     'git\npush origin "main'),
        ]
        for label, cmd in deny_main:
            results.append(run_case(label, "DENY", cmd, main_repo))

        # --- Shell-eval-construct fail-closed (codex re-review) ---
        # Run on the FEATURE repo (HEAD=feature) so a pass proves the deny comes
        # from the construct rule, not from HEAD==main: a static tokenizer cannot
        # resolve these to a dst, so any push/commit carrying one is denied.
        deny_eval = [
            ("cmd-subst $(printf git) push",   "$(printf git) $(printf push) origin main"),
            ("backtick dst",                   "git push origin `echo main`"),
            ("var-expansion dst $B",           "B=main; git push origin $B"),
            ("eval-wrapped push",              'eval "git push origin main"'),
            ("sh -c push",                     'sh -c "git push origin main"'),
            # Codex r2: construct fragments the word "push" itself
            ("word-build p$(printf us)h",      "git p$(printf us)h origin main"),
            ("word-build $(cmd)push suffix",   "git $(echo pu)sh origin main"),
            # Opus r4: path-qualified git binary
            ("abs path /usr/bin/git push",    "/usr/bin/git push origin main"),
            ("rel path ./git push",           "./git push origin main"),
            ("homebrew git push",             "/opt/homebrew/bin/git push origin main"),
            # Opus r3: ANSI-C quoting $'push' bypasses construct detect
            ("ANSI-C $'push' quoting",        "git $'push' origin main"),
            # Sonnet r3: --mirror / --all push all branches
            ("push --mirror (feat HEAD)",      "git push --mirror"),
            ("push --mirror origin (feat)",    "git push --mirror origin"),
            ("push --all origin (feat)",       "git push --all origin"),
            ("push origin --all (feat)",       "git push origin --all"),
            # Sonnet r3: case-insensitive branch names
            ("push origin Main",              "git push origin Main"),
            ("push origin MAIN",              "git push origin MAIN"),
            ("push REFS/HEADS/main",          "git push origin REFS/HEADS/main"),
            # Sonnet r3: backslash-newline continuation
            ("push origin \\nmain (cont.)",   "git push origin \\\nmain"),
            # Sonnet r4 P3: --delete is a flag (skipped); main stays the
            # positional dst → deny.  Feature repo proves dst-gating, not HEAD.
            ("push origin --delete main",     "git push origin --delete main"),
        ]
        for label, cmd in deny_eval:
            results.append(run_case(label, "DENY", cmd, feat_repo))

        # --- ALLOW cases ---
        # Feature-branch push while HEAD=main (gates on DST, not HEAD).
        results.append(run_case(
            "push feature branch while HEAD=main", "ALLOW",
            "git push origin feature/x", main_repo))
        # Bare push while HEAD is a feature branch.
        results.append(run_case(
            "bare push while HEAD=feature", "ALLOW",
            "git push", feat_repo))
        # AUTO_PILOT_MAIN_OK env bypass.
        results.append(run_case(
            "AUTO_PILOT_MAIN_OK=1 env bypass", "ALLOW",
            "git push origin main", main_repo,
            env_extra={"AUTO_PILOT_MAIN_OK": "1"}))
        # AUTO_PILOT_MAIN_OK command-prefix bypass.
        results.append(run_case(
            "AUTO_PILOT_MAIN_OK=1 cmd-prefix bypass", "ALLOW",
            "AUTO_PILOT_MAIN_OK=1 git push origin main", main_repo))
        # Non-push/commit git command → ALLOW (no false fire).
        results.append(run_case(
            "git status (non push/commit)", "ALLOW",
            "git status", main_repo))
        # Construct in non-push command → ALLOW (no over-fire).
        results.append(run_case(
            "construct + git status (no push)", "ALLOW",
            "echo $(date); git status", feat_repo))
        results.append(run_case(
            "commit with construct (no push word)", "ALLOW",
            "git commit -m '$(date)'", feat_repo))
        # Quoted subshell on feature branch bare push → ALLOW.
        results.append(run_case(
            "subshell bare push on feature", "ALLOW",
            "(git push)", feat_repo))
        # Documented residual: unbalanced quote fail-closed resolves to
        # __CURRENT__ (HEAD), so on a feature branch it allows — the literal
        # "main" in the broken token is NOT treated as dst.
        results.append(run_case(
            "unbalanced quote on feature (residual)", "ALLOW",
            'git push origin "main', feat_repo))

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

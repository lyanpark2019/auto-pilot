#!/usr/bin/env python3
"""Test runner for doc-sync-update.sh hook.

Script-style (not pytest): invokes the hook via subprocess with JSON on stdin,
mirrors hooks/test_pre_edit_human_only.py pattern.

Covers:
  1.  empty stdin → exit 0, no side effect
  2.  no/malformed file_path → exit 0, no side effect
  3.  relative file_path → exit 0, no flag touched
  4.  code file in dir containing graphify-out/ → needs_update created; exit 0
  5.  code file with no graphify-out/ ancestor → no flag; exit 0
  6.  code file under skipped/generated dir (node_modules) → no flag; exit 0
  7.  non-code non-md extension (.txt) → exit 0, no flag
  8.  .md under .../sources/ with fake GRAPHIFY_BIN + default GRAPHIFY_VAULT_AUTOSYNC
      → fake graphify invoked (sentinel written); exit 0; code branch NOT reached
  9.  .md under sources/ with GRAPHIFY_VAULT_AUTOSYNC=0 → graphify NOT invoked
 10a. GRAPHIFY_AUTOSYNC=1, fake-success graphify → flag removed after update
 10b. GRAPHIFY_AUTOSYNC=1, fake-fail graphify → flag remains + exit 0 (fail-open)
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HOOK = str(Path(__file__).parent / "doc-sync-update.sh")


def _make_fake_graphify(tmp: str, exit_code: int = 0, sentinel_file: str = "") -> str:
    """Write a tiny fake graphify executable; returns its path."""
    script = "#!/bin/sh\n"
    if sentinel_file:
        script += f"touch {sentinel_file!r}\n"
    script += f"exit {exit_code}\n"
    path = os.path.join(tmp, "fake_graphify")
    Path(path).write_text(script)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def run(
    label: str,
    stdin_text: str,
    env_extra: dict[str, Any] | None = None,
    expect_rc: int = 0,
) -> tuple[bool, subprocess.CompletedProcess[str]]:
    """Run the hook and return (passed, result)."""
    env = os.environ.copy()
    # Strip inherited autosync vars so tests are hermetic
    env.pop("GRAPHIFY_AUTOSYNC", None)
    env.pop("GRAPHIFY_VAULT_AUTOSYNC", None)
    env.pop("GRAPHIFY_BIN", None)
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["bash", HOOK],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )
    ok = result.returncode == expect_rc
    icon = "OK  " if ok else "FAIL"
    print(f"[{icon}] {label}")
    if not ok:
        print(f"       expected rc={expect_rc}, got rc={result.returncode}")
        print(f"       stderr: {result.stderr.strip()!r}")
    return ok, result


def main() -> None:
    results: list[bool] = []

    # ── Case 1: empty stdin ───────────────────────────────────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        ok, _ = run("1. empty stdin → exit 0, no side effect", stdin_text="")
        results.append(ok)

    # ── Case 2: malformed file_path (no file_path key) ───────────────────────
    with tempfile.TemporaryDirectory() as tmp:
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"command": "ls"}})
        ok, _ = run("2. no file_path key → exit 0, no side effect", stdin_text=payload)
        results.append(ok)

    # ── Case 3: relative file_path → skip (needs absolute path) ─────────────
    with tempfile.TemporaryDirectory() as tmp:
        # Put a graphify-out/ in the tmp dir but use a relative path → hook skips
        (Path(tmp) / "graphify-out").mkdir()
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": "relative/path/foo.py"}}
        )
        ok, _ = run("3. relative file_path → exit 0, no flag touched", stdin_text=payload)
        flag = Path(tmp) / "graphify-out" / "needs_update"
        if flag.exists():
            print("       FAIL: needs_update was created (should not be)")
            ok = False
        results.append(ok)

    # ── Case 4: code file in dir containing graphify-out/ → flag created ─────
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "myrepo"
        repo.mkdir()
        graph_out = repo / "graphify-out"
        graph_out.mkdir()
        src = repo / "src"
        src.mkdir()
        code_file = src / "main.py"
        code_file.write_text("x = 1\n")
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(code_file)}}
        )
        ok, _ = run(
            "4. code file in repo with graphify-out/ → needs_update created; exit 0",
            stdin_text=payload,
        )
        flag = graph_out / "needs_update"
        if not flag.exists():
            print("       FAIL: needs_update was NOT created")
            ok = False
        results.append(ok)

    # ── Case 5: code file with no graphify-out/ ancestor → no flag ───────────
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "project" / "src"
        src.mkdir(parents=True)
        code_file = src / "utils.py"
        code_file.write_text("y = 2\n")
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(code_file)}}
        )
        ok, _ = run(
            "5. code file with no graphify-out/ ancestor → no flag; exit 0",
            stdin_text=payload,
        )
        # Confirm no needs_update anywhere under tmp
        found = list(Path(tmp).rglob("needs_update"))
        if found:
            print(f"       FAIL: unexpected needs_update files: {found}")
            ok = False
        results.append(ok)

    # ── Case 6: code file under node_modules (skipped dir) → no flag ─────────
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / "graphify-out").mkdir(parents=True)
        nm = repo / "node_modules" / "lib"
        nm.mkdir(parents=True)
        code_file = nm / "index.js"
        code_file.write_text("module.exports = {};\n")
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(code_file)}}
        )
        ok, _ = run(
            "6. code file under node_modules → no flag; exit 0",
            stdin_text=payload,
        )
        flag = repo / "graphify-out" / "needs_update"
        if flag.exists():
            print("       FAIL: needs_update was created (should be skipped)")
            ok = False
        results.append(ok)

    # ── Case 7: non-code non-md extension (.txt) → exit 0, no flag ───────────
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        (repo / "graphify-out").mkdir(parents=True)
        txt_file = repo / "notes.txt"
        txt_file.write_text("hello\n")
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(txt_file)}}
        )
        ok, _ = run(
            "7. .txt file (non-code non-md) → exit 0, no flag",
            stdin_text=payload,
        )
        flag = repo / "graphify-out" / "needs_update"
        if flag.exists():
            print("       FAIL: needs_update was created for .txt file")
            ok = False
        results.append(ok)

    # ── Case 8: .md under .../sources/ + fake graphify → sentinel written ─────
    with tempfile.TemporaryDirectory() as tmp:
        # Layout: <tmp>/vault/sources/note.md
        sources_dir = Path(tmp) / "vault" / "sources"
        sources_dir.mkdir(parents=True)
        md_file = sources_dir / "note.md"
        md_file.write_text("# Note\n")
        sentinel = os.path.join(tmp, "graphify_called")
        fake_bin = _make_fake_graphify(tmp, exit_code=0, sentinel_file=sentinel)
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(md_file)}}
        )
        ok, _ = run(
            "8. .md under sources/ + fake graphify → sentinel written; exit 0",
            stdin_text=payload,
            env_extra={"GRAPHIFY_BIN": fake_bin},
        )
        if not Path(sentinel).exists():
            print("       FAIL: fake graphify was NOT invoked (sentinel absent)")
            ok = False
        # Also confirm code branch is NOT triggered (no needs_update anywhere)
        found = list(Path(tmp).rglob("needs_update"))
        if found:
            print(f"       FAIL: needs_update exists (code branch triggered): {found}")
            ok = False
        results.append(ok)

    # ── Case 9: .md under sources/ with GRAPHIFY_VAULT_AUTOSYNC=0 → NOT invoked
    with tempfile.TemporaryDirectory() as tmp:
        sources_dir = Path(tmp) / "vault" / "sources"
        sources_dir.mkdir(parents=True)
        md_file = sources_dir / "note.md"
        md_file.write_text("# Note\n")
        sentinel = os.path.join(tmp, "graphify_called")
        fake_bin = _make_fake_graphify(tmp, exit_code=0, sentinel_file=sentinel)
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(md_file)}}
        )
        ok, _ = run(
            "9. .md under sources/ with GRAPHIFY_VAULT_AUTOSYNC=0 → NOT invoked; exit 0",
            stdin_text=payload,
            env_extra={
                "GRAPHIFY_BIN": fake_bin,
                "GRAPHIFY_VAULT_AUTOSYNC": "0",
            },
        )
        if Path(sentinel).exists():
            print("       FAIL: fake graphify WAS invoked (should be suppressed by AUTOSYNC=0)")
            ok = False
        results.append(ok)

    # ── Case 10a: GRAPHIFY_AUTOSYNC=1 + fake-success → flag removed ──────────
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        graph_out = repo / "graphify-out"
        graph_out.mkdir(parents=True)
        src = repo / "src"
        src.mkdir()
        code_file = src / "app.ts"
        code_file.write_text("const x = 1;\n")
        sentinel = os.path.join(tmp, "graphify_called")
        fake_bin = _make_fake_graphify(tmp, exit_code=0, sentinel_file=sentinel)
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(code_file)}}
        )
        ok, _ = run(
            "10a. GRAPHIFY_AUTOSYNC=1 + fake-success → flag removed; exit 0",
            stdin_text=payload,
            env_extra={
                "GRAPHIFY_BIN": fake_bin,
                "GRAPHIFY_AUTOSYNC": "1",
            },
        )
        flag = graph_out / "needs_update"
        if flag.exists():
            print("       FAIL: needs_update still exists after fake-success graphify run")
            ok = False
        if not Path(sentinel).exists():
            print("       FAIL: fake graphify was NOT called (sentinel absent)")
            ok = False
        results.append(ok)

    # ── Case 10b: GRAPHIFY_AUTOSYNC=1 + fake-fail → flag remains, exit 0 ─────
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        graph_out = repo / "graphify-out"
        graph_out.mkdir(parents=True)
        src = repo / "src"
        src.mkdir()
        code_file = src / "app.go"
        code_file.write_text("package main\n")
        sentinel = os.path.join(tmp, "graphify_called")
        fake_bin = _make_fake_graphify(tmp, exit_code=1, sentinel_file=sentinel)
        payload = json.dumps(
            {"tool_name": "Edit", "tool_input": {"file_path": str(code_file)}}
        )
        ok, _ = run(
            "10b. GRAPHIFY_AUTOSYNC=1 + fake-fail → flag remains; exit 0 (fail-open)",
            stdin_text=payload,
            env_extra={
                "GRAPHIFY_BIN": fake_bin,
                "GRAPHIFY_AUTOSYNC": "1",
            },
        )
        flag = graph_out / "needs_update"
        if not flag.exists():
            print("       FAIL: needs_update was removed despite graphify failure")
            ok = False
        if not Path(sentinel).exists():
            print("       FAIL: fake graphify was NOT called")
            ok = False
        results.append(ok)

    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

"""shellcheck-on-write.sh — advisory shellcheck on session-written *.sh files."""
from __future__ import annotations

import subprocess
from pathlib import Path

from _hook_helpers import _run_hook

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "hooks" / "shellcheck-on-write.sh"

# SC2164 (warning): Use 'cd ... || exit' — triggers at -S warning level.
BAD_SH = '#!/bin/bash\ncd /tmp\necho done\n'


def test_non_sh_file_silent(tmp_path):
    f = tmp_path / "x.py"
    f.write_text("print(1)\n")
    r = _run_hook(HOOK, {"tool_input": {"file_path": str(f)}}, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stderr == ""


def test_sh_with_warning_reports_advisory(tmp_path):
    f = tmp_path / "x.sh"
    f.write_text(BAD_SH)
    r = _run_hook(HOOK, {"tool_input": {"file_path": str(f)}}, cwd=tmp_path)
    assert r.returncode == 0          # advisory: never blocks
    assert "SC" in r.stderr           # shellcheck finding surfaced


def test_missing_shellcheck_binary_silent(tmp_path):
    f = tmp_path / "x.sh"
    f.write_text(BAD_SH)
    r = _run_hook(HOOK, {"tool_input": {"file_path": str(f)}}, cwd=tmp_path,
                  env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 0


def test_garbage_stdin_fail_open(tmp_path):
    r = subprocess.run([str(HOOK)], input="not json", capture_output=True,
                       text=True, cwd=str(tmp_path), timeout=15)
    assert r.returncode == 0

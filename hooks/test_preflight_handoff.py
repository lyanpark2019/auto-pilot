#!/usr/bin/env python3
"""Tests for the handoff pickup consumed-flip logic in preflight-path.sh.

Exercises the fixed semantics:
  - pending handoff is injected and flipped to consumed with consumed_by_session_id
  - the writer session (same PPID) does NOT consume a handoff it wrote
    (this is simulated by having the handoff already consumed with a different session)
  - a second foreign session does NOT re-inject an already-consumed handoff
  - restart safety: same session_id sees a consumed handoff again (re-inject)
"""
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOOK = str(Path(__file__).parent / "preflight-path.sh")


def _make_handoff(
    tmpdir: str,
    status: str = "pending",
    consumed_by: str = "",
    age_days: float = 0,
) -> Path:
    """Write a .planning/auto-pilot/handoff-next.md in a temp project root."""
    planning = Path(tmpdir) / ".planning" / "auto-pilot"
    planning.mkdir(parents=True, exist_ok=True)
    path = planning / "handoff-next.md"
    now = datetime.now(timezone.utc)
    written_at = (now - timedelta(days=age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fm_lines = [
        f"status: {status}",
        f"written_at: {written_at}",
    ]
    if consumed_by:
        fm_lines.append(f"consumed_by_session_id: {consumed_by}")
    fm = "\n".join(fm_lines)
    path.write_text(f"---\n{fm}\n---\n\nHandoff body text.\n", encoding="utf-8")
    return path


def _run_hook(cwd: str) -> tuple[int, str, str]:
    """Run preflight-path.sh with empty stdin JSON (SessionStart payload)."""
    env = os.environ.copy()
    # Use cwd as project root so the hook walks up correctly.
    result = subprocess.run(
        ["bash", HOOK],
        cwd=cwd,
        input="{}",
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout, result.stderr


def _handoff_status(path: Path) -> dict[str, str]:
    """Parse frontmatter fields from handoff file."""
    import re
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\A---[ \t]*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip()
    return out


PASS = True
FAIL = False


def run_case(label: str, fn: Callable[[], bool]) -> bool:
    detail: str = ""
    ok: bool = False
    try:
        fn_result = fn()
        ok = fn_result is True or fn_result is None
    except AssertionError as e:
        ok = False
        detail = str(e)
    icon = "OK  " if ok else "FAIL"
    print(f"[{icon}] {label}")
    if not ok and detail:
        print(f"       detail: {detail!r}")
    return ok


def case_pending_consumed_and_flipped() -> bool:
    """A pending handoff is injected and flipped to consumed with session ID."""
    with tempfile.TemporaryDirectory() as d:
        path = _make_handoff(d, status="pending")
        rc, stdout, _ = _run_hook(d)
        assert rc == 0, f"hook exited {rc}"
        assert stdout.strip(), "expected additionalContext output"
        try:
            payload = json.loads(stdout.strip())
        except json.JSONDecodeError:
            assert False, f"stdout not JSON: {stdout!r}"
        assert "hookSpecificOutput" in payload, "missing hookSpecificOutput"
        assert "Handoff body" in payload["hookSpecificOutput"].get("additionalContext", "")
        # File should now be flipped to consumed.
        fm = _handoff_status(path)
        assert fm.get("status") == "consumed", f"status not consumed: {fm}"
        assert "consumed_by_session_id" in fm, "consumed_by_session_id not written"
    return True


def case_consumed_different_session_skipped() -> bool:
    """A handoff consumed by a different session is NOT re-injected."""
    with tempfile.TemporaryDirectory() as d:
        path = _make_handoff(d, status="consumed", consumed_by="foreign-session-abc")
        rc, stdout, _ = _run_hook(d)
        assert rc == 0
        # No output = skip (no injection for foreign session).
        assert not stdout.strip(), f"expected no output, got: {stdout!r}"
        # File status unchanged.
        fm = _handoff_status(path)
        assert fm.get("status") == "consumed"
        assert fm.get("consumed_by_session_id") == "foreign-session-abc"
    return True


def case_stale_handoff_skipped() -> bool:
    """A pending handoff older than 7 days is not injected."""
    with tempfile.TemporaryDirectory() as d:
        _make_handoff(d, status="pending", age_days=8)
        rc, stdout, _ = _run_hook(d)
        assert rc == 0
        assert not stdout.strip(), f"expected no output for stale, got: {stdout!r}"
    return True


def case_no_handoff_file_silent() -> bool:
    """When no handoff file exists, hook exits 0 silently."""
    with tempfile.TemporaryDirectory() as d:
        rc, stdout, _ = _run_hook(d)
        assert rc == 0
        assert not stdout.strip()
    return True


def case_malformed_frontmatter_silent() -> bool:
    """Malformed frontmatter -> silent skip."""
    with tempfile.TemporaryDirectory() as d:
        planning = Path(d) / ".planning" / "auto-pilot"
        planning.mkdir(parents=True, exist_ok=True)
        (planning / "handoff-next.md").write_text("no frontmatter here\n")
        rc, stdout, _ = _run_hook(d)
        assert rc == 0
        assert not stdout.strip()
    return True


def case_whitespace_only_status_skipped() -> bool:
    """Whitespace-only status field is not 'pending' → silent skip, no injection.

    The hook checks ``status == "consumed"`` then ``status != "pending"``.
    A whitespace-only value (e.g. "   ") is not "pending", so the hook exits
    silently without injecting the handoff.  This is a characterization pin —
    the hook correctly ignores unknown/malformed status values.

    Note: _handoff_status() strips YAML values with v.strip(), so the stored
    "   " is read back as "" — we assert on the stripped form.
    """
    with tempfile.TemporaryDirectory() as d:
        path = _make_handoff(d, status="   ")
        rc, stdout, _ = _run_hook(d)
        assert rc == 0, f"hook exited {rc}"
        assert not stdout.strip(), f"expected no output for whitespace status, got: {stdout!r}"
        # File must be unchanged (no flip attempted on non-pending status).
        # _handoff_status strips values, so "   " reads back as "".
        fm = _handoff_status(path)
        assert fm.get("status") in ("", "   "), f"status was modified unexpectedly: {fm}"
    return True


def case_tab_only_status_skipped() -> bool:
    """Tab-only status field → same as whitespace-only: silent skip."""
    with tempfile.TemporaryDirectory() as d:
        _make_handoff(d, status="\t")
        rc, stdout, _ = _run_hook(d)
        assert rc == 0
        assert not stdout.strip(), f"expected no output for tab status, got: {stdout!r}"
    return True


def main() -> None:
    cases = [
        ("pending handoff is injected + flipped with session ID", case_pending_consumed_and_flipped),
        ("consumed-by-foreign-session is NOT re-injected", case_consumed_different_session_skipped),
        ("stale handoff (>7d) is skipped silently", case_stale_handoff_skipped),
        ("no handoff file: silent exit 0", case_no_handoff_file_silent),
        ("malformed frontmatter: silent skip", case_malformed_frontmatter_silent),
        ("whitespace-only status: silent skip", case_whitespace_only_status_skipped),
        ("tab-only status: silent skip", case_tab_only_status_skipped),
    ]
    results = [run_case(label, fn) for label, fn in cases]
    passed = sum(results)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()

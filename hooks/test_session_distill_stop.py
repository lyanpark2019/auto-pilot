#!/usr/bin/env python3
"""Test runner for session-distill-stop.sh Stop hook.

Feeds Stop-payload JSON via stdin.  Every hook invocation runs with HOME set to
a fresh temporary directory so the real ~/Documents/Obsidian vault is never
touched.  The target repo root is supplied two ways the hook supports:
CLAUDE_PROJECT_DIR (env) or the payload's `cwd`.

Advisory contract: exit 0 on every path; the session page is written ONLY when
an auto-pilot run is detected (state.json present) and the payload is not a
Stop reentry.

ANTI-FABRICATION: every case that asserts on page content drives the REAL hook
subprocess as the producer and asserts on the page IT writes — the test never
hand-writes a page and asserts on its own fabricated shape.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = str(Path(__file__).parent / "session-distill-stop.sh")


def _seed_state(root: Path, run_id: str = "rTEST42") -> None:
    planning = root / ".planning" / "auto-pilot"
    planning.mkdir(parents=True, exist_ok=True)
    (planning / "state.json").write_text(json.dumps({"run_id": run_id}))


def _session_pages(vault: Path) -> list[Path]:
    sessions_dir = vault / "sessions"
    if not sessions_dir.is_dir():
        return []
    return list(sessions_dir.glob("session-*.md"))


def _run_hook(
    payload: object,
    *,
    root: Path,
    root_via: str,
    home: Path,
    vault_path: Path | None = None,
    obsidian_root: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("NBM_VAULT_PATH", None)
    env.pop("VAULT_BUILDER_VAULT", None)
    env.pop("VB_OBSIDIAN_ROOT", None)
    env["HOME"] = str(home)

    if root_via == "env":
        env["CLAUDE_PROJECT_DIR"] = str(root)
        stdin_payload = payload
    else:  # "cwd": root injected into payload
        stdin_payload = dict(payload) if isinstance(payload, dict) else payload
        if isinstance(stdin_payload, dict):
            stdin_payload["cwd"] = str(root)

    if vault_path is not None:
        env["NBM_VAULT_PATH"] = str(vault_path)
    if obsidian_root is not None:
        env["VB_OBSIDIAN_ROOT"] = str(obsidian_root)

    stdin = stdin_payload if isinstance(stdin_payload, str) else json.dumps(stdin_payload)
    return subprocess.run(
        ["bash", HOOK], input=stdin, capture_output=True, text=True, env=env
    )


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Parse YAML frontmatter between --- delimiters into a dict."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


def case_reentry_guard() -> bool:
    """stop_hook_active=true → no page written, exit 0."""
    label = "reentry guard (stop_hook_active)"
    with (
        tempfile.TemporaryDirectory() as root_s,
        tempfile.TemporaryDirectory() as vault_s,
        tempfile.TemporaryDirectory() as home_s,
    ):
        root = Path(root_s)
        vault = Path(vault_s)
        _seed_state(root)
        result = _run_hook(
            {"stop_hook_active": True},
            root=root,
            root_via="env",
            home=Path(home_s),
            vault_path=vault,
        )
        pages = _session_pages(vault)
        ok = result.returncode == 0 and len(pages) == 0
    _report(label, ok, result, expect_pages=0, got_pages=len(pages))
    return ok


def case_no_state_json() -> bool:
    """No state.json → no-op, no page written, exit 0."""
    label = "no state.json → no-op"
    with (
        tempfile.TemporaryDirectory() as root_s,
        tempfile.TemporaryDirectory() as vault_s,
        tempfile.TemporaryDirectory() as home_s,
    ):
        root = Path(root_s)
        vault = Path(vault_s)
        # deliberately do NOT call _seed_state
        result = _run_hook({}, root=root, root_via="env", home=Path(home_s), vault_path=vault)
        pages = _session_pages(vault)
        ok = result.returncode == 0 and len(pages) == 0
    _report(label, ok, result, expect_pages=0, got_pages=len(pages))
    return ok


def case_active_run_env_root() -> bool:
    """Active run, env root, NBM_VAULT_PATH → one page; assert frontmatter fields."""
    label = "active run (env root, NBM_VAULT_PATH) → page + frontmatter"
    with (
        tempfile.TemporaryDirectory() as root_s,
        tempfile.TemporaryDirectory() as vault_s,
        tempfile.TemporaryDirectory() as transcript_s,
        tempfile.TemporaryDirectory() as home_s,
    ):
        root = Path(root_s)
        vault = Path(vault_s)
        # Create a real transcript file so raw_transcript path resolves
        transcript_file = Path(transcript_s) / "session.jsonl"
        transcript_file.write_text('{"role":"user","content":"hello"}\n')

        _seed_state(root, run_id="rTEST42")
        result = _run_hook(
            {"transcript_path": str(transcript_file), "session_id": "ses-abc123"},
            root=root,
            root_via="env",
            home=Path(home_s),
            vault_path=vault,
        )
        pages = _session_pages(vault)
        ok = result.returncode == 0 and len(pages) == 1
        if ok:
            fm = _parse_frontmatter(pages[0].read_text(encoding="utf-8"))
            ok = (
                fm.get("run_id") == "rTEST42"
                and fm.get("session_id") == "ses-abc123"
                and fm.get("date") != ""
                and fm.get("raw_transcript") == str(transcript_file)
                and os.path.exists(fm.get("raw_transcript", ""))
            )
    _report(label, ok, result, expect_pages=1, got_pages=len(pages))
    return ok


def case_active_run_payload_cwd() -> bool:
    """Active run, root via payload cwd (env unset) → page written, exit 0."""
    label = "active run (payload cwd, env unset) → page written"
    with (
        tempfile.TemporaryDirectory() as root_s,
        tempfile.TemporaryDirectory() as vault_s,
        tempfile.TemporaryDirectory() as home_s,
    ):
        root = Path(root_s)
        vault = Path(vault_s)
        _seed_state(root)
        result = _run_hook(
            {"session_id": "ses-payload-cwd"},
            root=root,
            root_via="cwd",
            home=Path(home_s),
            vault_path=vault,
        )
        pages = _session_pages(vault)
        ok = result.returncode == 0 and len(pages) == 1
    _report(label, ok, result, expect_pages=1, got_pages=len(pages))
    return ok


def case_garbage_stdin() -> bool:
    """Garbage stdin + no state.json → fail-open rc 0, no page."""
    label = "garbage stdin + no state → fail-open, no page"
    with (
        tempfile.TemporaryDirectory() as root_s,
        tempfile.TemporaryDirectory() as vault_s,
        tempfile.TemporaryDirectory() as home_s,
    ):
        root = Path(root_s)
        vault = Path(vault_s)
        # No state.json seeded — activation guard fires first
        result = _run_hook(
            "not json at all",
            root=root,
            root_via="env",
            home=Path(home_s),
            vault_path=vault,
        )
        pages = _session_pages(vault)
        ok = result.returncode == 0 and len(pages) == 0
    _report(label, ok, result, expect_pages=0, got_pages=len(pages))
    return ok


def case_idempotency() -> bool:
    """Same session_id run twice → still exactly one page (session_id-keyed filename)."""
    label = "idempotency: same session_id twice → one page"
    with (
        tempfile.TemporaryDirectory() as root_s,
        tempfile.TemporaryDirectory() as vault_s,
        tempfile.TemporaryDirectory() as home_s,
    ):
        root = Path(root_s)
        vault = Path(vault_s)
        _seed_state(root)
        payload = json.dumps({"session_id": "ses-idempotent"})
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        env.pop("NBM_VAULT_PATH", None)
        env.pop("VAULT_BUILDER_VAULT", None)
        env.pop("VB_OBSIDIAN_ROOT", None)
        env["HOME"] = home_s
        env["CLAUDE_PROJECT_DIR"] = str(root)
        env["NBM_VAULT_PATH"] = str(vault)
        r1 = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True, env=env)
        r2 = subprocess.run(["bash", HOOK], input=payload, capture_output=True, text=True, env=env)
        pages = _session_pages(vault)
        ok = (
            r1.returncode == 0
            and r2.returncode == 0
            and len(pages) == 1
            and pages[0].name == "session-ses-idempotent.md"
        )
    _report(label, ok, r2, expect_pages=1, got_pages=len(pages))
    return ok


def case_vault_fallback() -> bool:
    """VB_OBSIDIAN_ROOT fallback: page lands at <obsidian_root>/<project>/sessions/."""
    label = "vault fallback (VB_OBSIDIAN_ROOT) → page in <root_name>/sessions/"
    with (
        tempfile.TemporaryDirectory() as root_s,
        tempfile.TemporaryDirectory() as obsidian_s,
        tempfile.TemporaryDirectory() as home_s,
    ):
        root = Path(root_s)
        obsidian_root = Path(obsidian_s)
        _seed_state(root)
        result = _run_hook(
            {"session_id": "ses-fallback"},
            root=root,
            root_via="env",
            home=Path(home_s),
            vault_path=None,
            obsidian_root=obsidian_root,
        )
        expected_vault = obsidian_root / root.name
        pages = _session_pages(expected_vault)
        ok = result.returncode == 0 and len(pages) == 1
    _report(label, ok, result, expect_pages=1, got_pages=len(pages))
    return ok


def case_true_default_vault() -> bool:
    """No vault env at all: page lands at <HOME>/Documents/Obsidian/<root>/sessions/."""
    label = "true default vault ($HOME/Documents/Obsidian) → page, no real-vault leak"
    with (
        tempfile.TemporaryDirectory() as root_s,
        tempfile.TemporaryDirectory() as home_s,
    ):
        root = Path(root_s)
        home = Path(home_s)
        _seed_state(root)
        # _run_hook with vault_path=None and obsidian_root=None — no vault env set,
        # so the hook falls back to $HOME/Documents/Obsidian/<root.name>.
        result = _run_hook(
            {"session_id": "ses-default-vault"},
            root=root,
            root_via="env",
            home=home,
            vault_path=None,
            obsidian_root=None,
        )
        expected_vault = home / "Documents" / "Obsidian" / root.name
        pages = _session_pages(expected_vault)
        ok = result.returncode == 0 and len(pages) == 1
        if ok:
            ok = pages[0].name == "session-ses-default-vault.md"
    _report(label, ok, result, expect_pages=1, got_pages=len(pages))
    return ok


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report(
    label: str,
    ok: bool,
    result: subprocess.CompletedProcess[str],
    *,
    expect_pages: int,
    got_pages: int,
) -> None:
    icon = "OK  " if ok else "FAIL"
    print(
        f"[{icon}] {label:55s} expect_pages={expect_pages} got_pages={got_pages} rc={result.returncode}"
    )
    if not ok:
        print(f"       stdout: {result.stdout.strip()!r}")
        print(f"       stderr: {result.stderr.strip()!r}")


def main() -> None:
    cases = [
        case_reentry_guard,
        case_no_state_json,
        case_active_run_env_root,
        case_active_run_payload_cwd,
        case_garbage_stdin,
        case_idempotency,
        case_vault_fallback,
        case_true_default_vault,
    ]
    results = [c() for c in cases]
    passed = sum(results)
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()

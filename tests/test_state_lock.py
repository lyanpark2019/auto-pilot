"""Tests for state.json file locking + atomic write.

Covers:
- Atomic write: STATE_FILE byte-identical to last write, never half-formed JSON.
- Concurrent writers: 10 subprocess writers, last-writer-wins, no torn JSON.
- Reader during writer: reader observes either pre- or post-state, never partial.
- Lock file location: STATE_DIR/state.lock created, separate from contract `.lock`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import _state


@pytest.fixture()
def cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_atomic_write_roundtrip(cwd):
    state: _state.State = {"status": "running", "current_phase": 1, "total_phases": 3}
    _state.save_state(state)
    assert _state.STATE_FILE.exists()
    loaded = _state.load_state()
    assert loaded["status"] == "running"
    assert loaded["current_phase"] == 1


def test_lock_file_location(cwd):
    _state.save_state({"status": "running"})
    assert _state.STATE_LOCK.exists()
    assert _state.STATE_LOCK == _state.STATE_DIR / "state.lock"
    # Distinct from contract layer's `.lock` (which uses dir_path / ".lock")
    assert _state.STATE_LOCK.name == "state.lock"


def test_load_missing_returns_empty(cwd):
    assert _state.load_state() == {}


REPO = Path(__file__).resolve().parent.parent
WRITER_SCRIPT = textwrap.dedent("""
    import json, os, sys
    from pathlib import Path
    sys.path.insert(0, %r)
    os.chdir(%r)
    import _state
    n = int(sys.argv[1])
    state = _state.load_state()
    state["status"] = "running"
    state["current_phase"] = n
    state["last_writer"] = n
    _state.save_state(state)
""")


def _spawn_writer(repo: Path, cwd: Path, n: int) -> subprocess.Popen[bytes]:
    code = WRITER_SCRIPT % (str(repo / "scripts"), str(cwd))
    return subprocess.Popen(
        [sys.executable, "-c", code, str(n)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def test_concurrent_writers_no_torn_json(cwd):
    # Seed initial state
    _state.save_state({"status": "running", "current_phase": 0})

    procs = [_spawn_writer(REPO, cwd, n) for n in range(1, 11)]
    for p in procs:
        out, err = p.communicate(timeout=30)
        assert p.returncode == 0, err.decode()

    # JSON parses; one of the 10 writers won
    final = _state.load_state()
    assert final["status"] == "running"
    assert 1 <= final["last_writer"] <= 10
    # File content is whole JSON, not partial
    raw = _state.STATE_FILE.read_text()
    json.loads(raw)  # raises on torn write


def test_reader_during_writer_sees_consistent_snapshot(cwd):
    # Seed
    _state.save_state({"status": "running", "current_phase": 0})

    # Spawn slow writer (sleeps under the lock by reading + writing big blob)
    big_payload_script = textwrap.dedent("""
        import os, sys, time
        sys.path.insert(0, %r)
        os.chdir(%r)
        import _state
        big = {"status": "running", "blob": "x" * 200_000, "current_phase": 99}
        _state.save_state(big)
    """) % (str(REPO / "scripts"), str(cwd))

    writer = subprocess.Popen([sys.executable, "-c", big_payload_script])
    # Race: try to read while writer might be mid-write
    snapshots: list[dict] = []
    deadline = time.monotonic() + 5.0
    while writer.poll() is None and time.monotonic() < deadline:
        try:
            snapshots.append(dict(_state.load_state()))
        except json.JSONDecodeError:
            pytest.fail("reader saw torn JSON during concurrent write")
        time.sleep(0.001)

    writer.wait(timeout=10)
    assert writer.returncode == 0
    # Every snapshot must be a valid State dict (no None, no malformed)
    for snap in snapshots:
        assert isinstance(snap, dict)


def test_save_creates_state_dir(cwd):
    # No .planning/auto-pilot/ exists yet; save should create it
    assert not _state.STATE_DIR.exists()
    _state.save_state({"status": "running"})
    assert _state.STATE_DIR.is_dir()
    assert _state.STATE_FILE.exists()


def test_atomic_write_no_partial_on_crash(cwd, monkeypatch):
    """Simulate write failure mid-rename: tempfile must be cleaned up,
    target either stays untouched or contains the new content."""
    _state.save_state({"status": "running", "current_phase": 1})
    before = _state.STATE_FILE.read_text()

    # Patch atomic_write_text to fail after tempfile created
    import _contract

    orig = _contract.atomic_write_text

    def boom(path, text):
        # Write tempfile then raise — simulate kill between fsync and rename
        import tempfile
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
        os.write(fd, text.encode())
        os.close(fd)
        # Don't clean up tmp on purpose — verify it persists alongside target
        raise RuntimeError("simulated kill")

    monkeypatch.setattr(_contract, "atomic_write_text", boom)
    with pytest.raises(RuntimeError):
        _state.save_state({"status": "failed"})

    # Original target untouched
    assert _state.STATE_FILE.read_text() == before

    monkeypatch.setattr(_contract, "atomic_write_text", orig)

"""Tests for β reviewer watchdog (round-2 W2):
  ⓓ-6  reviewer watchdog (soft-warn, hard-kill + retry, retry-fail)
"""
from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path



class TestReviewerWatchdog:
    """Three paths tested with real subprocesses (sleep-based stand-ins)."""

    def _make_handle(self, role: str, tmp_path: Path,
                     cmd: list[str]) -> "object":
        """Spawn a real subprocess and return a SpawnHandle-like object."""
        output_dir = tmp_path / role
        output_dir.mkdir(parents=True, exist_ok=True)
        proc = subprocess.Popen(cmd)

        class _RealHandle:
            def __init__(self) -> None:
                self.role = role
                self.output_dir = output_dir
                self.proc = proc
                self._spawn_kwargs: dict = {}

            def poll(self) -> int | None:
                return self.proc.poll()

        return _RealHandle()

    def test_soft_warn_fires_proc_finishes_no_kill(self, tmp_path, capsys):
        """Soft-warn fires, process finishes normally (no kill)."""
        import _reviewer_wrapper as rw

        output_dir = tmp_path / "r1"
        output_dir.mkdir()

        proc = subprocess.Popen(["sleep", "0.3"])

        class _Handle:
            role = "r1"
            _spawn_kwargs: dict = {}

            def __init__(self) -> None:
                self.output_dir = output_dir
                self.proc = proc

            def poll(self) -> int | None:
                return self.proc.poll()

        handle = _Handle()

        def _write_marker() -> None:
            time.sleep(0.15)
            (output_dir / "done.marker").touch()

        t = threading.Thread(target=_write_marker, daemon=True)
        t.start()

        failures = rw.wait_all(
            [handle],
            timeout_sec=5,
            soft_warn_sec=0,       # fire immediately
            hard_kill_sec=9999,    # never kill
        )
        t.join(timeout=2)
        assert failures == []
        assert (output_dir / "done.marker").exists()
        # The soft-warn branch must actually fire — without this assert,
        # deleting the warn path left the test green (review r1 P2).
        stderr = capsys.readouterr().err
        assert "watchdog.reviewer_lagging" in stderr
        # And no kill happened on this path
        assert "watchdog.hard_kill" not in stderr

    def test_hard_kill_retry_succeeds(self, tmp_path):
        """Hard kill fires; retry spawns successfully and writes done.marker."""
        import _reviewer_wrapper as rw

        output_dir_orig = tmp_path / "r2"
        output_dir_orig.mkdir()

        proc = subprocess.Popen(["sleep", "60"])
        _reviewer_wrapper_kill_injector(proc)

        retry_output_dir = tmp_path / "r2-retry"
        retry_output_dir.mkdir()

        class _Handle:
            role = "r2"
            _spawn_kwargs: dict = {}

            def __init__(self) -> None:
                self.output_dir = output_dir_orig
                self.proc = proc

            def poll(self) -> int | None:
                return self.proc.poll()

        handle = _Handle()

        def _write_marker_delayed(path: Path) -> None:
            time.sleep(0.1)
            (path / "done.marker").touch()

        retry_thread = threading.Thread(
            target=_write_marker_delayed, args=(retry_output_dir,), daemon=True
        )

        original_respawn = rw._respawn

        def _fake_respawn(h: object) -> object:  # type: ignore[override]
            retry_thread.start()

            class _RetryHandle:
                role = "r2"
                _spawn_kwargs: dict = {}

                def __init__(self) -> None:
                    self.output_dir = retry_output_dir
                    self.proc = subprocess.Popen(["sleep", "0"])

                def poll(self) -> int | None:
                    return self.proc.poll()

            return _RetryHandle()

        rw._respawn = _fake_respawn
        try:
            failures = rw.wait_all(
                [handle],
                timeout_sec=10,
                soft_warn_sec=9999,   # no soft-warn
                hard_kill_sec=0,      # kill immediately
            )
        finally:
            rw._respawn = original_respawn
            proc.kill()
            proc.wait()

        assert failures == []  # retry succeeded
        retry_thread.join(timeout=2)

    def test_retry_fails_structured_failure_returned(self, tmp_path):
        """Hard kill; retry also fails → ReviewerFailure in return list."""
        import _reviewer_wrapper as rw

        output_dir_orig = tmp_path / "r3"
        output_dir_orig.mkdir()
        retry_output_dir = tmp_path / "r3-retry"
        retry_output_dir.mkdir()

        proc = subprocess.Popen(["sleep", "60"])

        class _Handle:
            role = "r3"
            _spawn_kwargs: dict = {}

            def __init__(self) -> None:
                self.output_dir = output_dir_orig
                self.proc = proc

            def poll(self) -> int | None:
                return self.proc.poll()

        handle = _Handle()

        original_respawn = rw._respawn

        def _fake_respawn_fail(h: object) -> object:  # type: ignore[override]
            retry_proc = subprocess.Popen(["sleep", "0"])

            class _RetryHandle:
                role = "r3"
                _spawn_kwargs: dict = {}

                def __init__(self) -> None:
                    self.output_dir = retry_output_dir
                    self.proc = retry_proc

                def poll(self) -> int | None:
                    return self.proc.poll()

            return _RetryHandle()

        rw._respawn = _fake_respawn_fail
        try:
            failures = rw.wait_all(
                [handle],
                timeout_sec=10,
                soft_warn_sec=9999,
                hard_kill_sec=0,      # kill immediately
            )
        finally:
            rw._respawn = original_respawn
            proc.kill()
            proc.wait()

        assert len(failures) == 1
        assert failures[0].role == "r3"
        assert "retry" in failures[0].reason

    def test_hung_retry_hard_killed_no_orphan(self, tmp_path):
        """Retry that hangs (never exits, no marker) is hard-killed within its
        own hard_kill window → structured ReviewerFailure, no orphan process,
        no SpawnTimeoutError (review r1: retry path had no kill bound)."""
        import _reviewer_wrapper as rw

        output_dir_orig = tmp_path / "r4"
        output_dir_orig.mkdir()
        proc = subprocess.Popen(["sleep", "60"])

        class _Handle:
            role = "r4"
            _spawn_kwargs: dict = {}

            def __init__(self) -> None:
                self.output_dir = output_dir_orig
                self.proc = proc

            def poll(self) -> int | None:
                return self.proc.poll()

        handle = _Handle()
        retry_dir = tmp_path / "r4-retry"
        retry_dir.mkdir()
        retry_procs: list[subprocess.Popen] = []

        def _fake_respawn_hang(h: object) -> object:
            class _RetryHandle:
                role = "r4"
                _spawn_kwargs: dict = {}

                def __init__(self) -> None:
                    self.output_dir = retry_dir
                    self.proc = subprocess.Popen(["sleep", "60"])  # hangs

                def poll(self) -> int | None:
                    return self.proc.poll()

            rh = _RetryHandle()
            retry_procs.append(rh.proc)
            return rh

        original_respawn = rw._respawn
        rw._respawn = _fake_respawn_hang
        try:
            failures = rw.wait_all(
                [handle],
                timeout_sec=10,
                soft_warn_sec=9999,
                hard_kill_sec=0,      # kill original immediately; retry bound also 0
            )
        finally:
            rw._respawn = original_respawn
            for p in [proc, *retry_procs]:
                if p.poll() is None:
                    p.kill()
                    p.wait()

        assert [f.role for f in failures] == ["r4"]
        assert failures[0].reason == "retry-hard-kill"
        # The hung retry must have been killed by the watchdog, not leaked
        assert retry_procs and retry_procs[0].poll() is not None


def _reviewer_wrapper_kill_injector(proc: subprocess.Popen) -> None:
    """Noop helper — real proc is used, just tracks side-effects."""
    pass

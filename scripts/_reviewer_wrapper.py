"""Parallel-safe subagent dispatch wrapper.

PM env-injection (os.environ[...] = ...) is process-global and would race
with concurrent reviewer dispatches. This wrapper spawns each reviewer as
a `claude -p` subprocess with an ISOLATED env dict — no shared state.

Hook (`pre-reviewer-write.sh`) reads AUTO_PILOT_SUBAGENT_ROLE +
AUTO_PILOT_OUTPUT_DIR from the spawned env; each subprocess sees only
its own.
"""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


class SpawnTimeoutError(Exception):
    """A spawned reviewer did not produce done.marker within timeout."""


@dataclass
class SpawnHandle:
    role: str
    ticket: Path
    output_dir: Path
    proc: subprocess.Popen[bytes]

    def poll(self) -> int | None:
        return self.proc.poll()


def spawn(*, role: str, ticket: Path, output_dir: Path,
          allowed_tools: str, disallowed_tools: str) -> SpawnHandle:
    """Spawn a `claude -p` subprocess for one reviewer dispatch.

    Subprocess env contains:
      - AUTO_PILOT_SUBAGENT_ROLE=<role>     (read by pre-reviewer-write.sh)
      - AUTO_PILOT_OUTPUT_DIR=<output_dir>  (read by pre-reviewer-write.sh)
    Parent env is NOT mutated.

    `--allowedTools` / `--disallowedTools` are real Claude Code CLI flags
    that constrain tool surface for this invocation only.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "AUTO_PILOT_SUBAGENT_ROLE": role,
        "AUTO_PILOT_OUTPUT_DIR": str(output_dir),
    }
    prompt = f"TICKET={ticket}\nRead ticket. Refuse if ticket_sha mismatch."
    cmd = [
        "claude", "-p",
        "--allowedTools", allowed_tools,
        "--disallowedTools", disallowed_tools,
        prompt,
    ]
    proc = subprocess.Popen(cmd, env=env)
    return SpawnHandle(role=role, ticket=ticket, output_dir=output_dir, proc=proc)


def wait_all(handles: list[SpawnHandle], *, timeout_sec: int) -> None:
    """Poll done.marker for every handle until all present, or timeout."""
    deadline = time.time() + timeout_sec
    remaining = list(handles)
    while remaining:
        for h in list(remaining):
            if (h.output_dir / "done.marker").exists():
                remaining.remove(h)
                continue
            if h.poll() is not None and not (h.output_dir / "done.marker").exists():
                remaining.remove(h)
                continue
        if not remaining:
            return
        if time.time() > deadline:
            roles = [getattr(h, "role", "?") for h in remaining]
            raise SpawnTimeoutError(
                f"timed out waiting for done.marker from {roles}"
            )
        time.sleep(0.1)

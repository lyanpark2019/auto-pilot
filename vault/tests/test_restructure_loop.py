from __future__ import annotations

from pathlib import Path

from scripts import restructure_loop
from scripts.restructure_phases._base import PhaseContext, PhaseResult


class _PassingPhase:
    name = "dummy"

    def __init__(self, ctx: PhaseContext) -> None:
        self.ctx = ctx

    def dry_run(self) -> str:
        return "dry dummy"

    def run(self) -> PhaseResult:
        return PhaseResult(status="completed", detail="done", artifacts={"artifact": "x"})

    def verify(self) -> tuple[bool, str]:
        return True, "ok"

    def rollback(self) -> None:
        raise AssertionError("rollback should not run")


def _ctx(tmp_path: Path, *, dry_run: bool = False) -> PhaseContext:
    return PhaseContext(
        obsidian_root=tmp_path / "obsidian",
        project_root=tmp_path / "project",
        plugin_root=tmp_path,
        state_path=tmp_path / "state" / "state.json",
        backup_dir=tmp_path / "backups",
        dry_run_mode=dry_run,
    )


def test_run_one_marks_completed_phase(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    state = {"phases": {}}

    assert restructure_loop.run_one(_PassingPhase, ctx, state)

    phase = state["phases"]["dummy"]
    assert phase["status"] == "completed"
    assert phase["detail"] == "done"
    assert phase["artifact"] == "x"
    assert ctx.state_path.exists()


def test_run_one_dry_run_marks_simulated(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path, dry_run=True)
    state = {"phases": {}}

    assert restructure_loop.run_one(_PassingPhase, ctx, state)

    assert state["phases"]["dummy"]["status"] == "dry_run_simulated"

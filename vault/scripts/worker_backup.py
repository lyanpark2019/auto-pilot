#!/usr/bin/env python3
"""Worker backup utility: .bak guarantee + rollback.

Workers should call:
    bak = WorkerBackup(vault, worker="vault-edge-curator", round_num=N, ticket_id=T)
    bak.snapshot(path)              # before destructive edit
    bak.snapshot_many([p1, p2])     # batch
    # ... mutate files ...
    bak.commit()                    # success: keep .bak for 1 round, then auto-purge
    # OR
    bak.rollback()                  # restore all snapshots

PM rollback (post-verifier-reject with score regression):
    WorkerBackup.rollback_ticket(vault, ticket_id)

Purge old .bak (per-round retention):
    WorkerBackup.purge_older_than_rounds(vault, keep_rounds=2)

.bak naming: <orig>.bak.<round>.<ticket_id>
Index: <vault>/meta/.backups.jsonl (append-only audit log)
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path


class WorkerBackup:
    """Represent WorkerBackup data for this module."""
    def __init__(self, vault: Path, worker: str, round_num: int, ticket_id: str):
        self.vault = Path(vault).expanduser().resolve()
        self.worker = worker
        self.round_num = round_num
        self.ticket_id = ticket_id
        self.index = self.vault / "meta" / ".backups.jsonl"
        self.index.parent.mkdir(parents=True, exist_ok=True)
        self._snapshots: list[tuple[Path, Path]] = []

    def snapshot(self, path: Path | str) -> Path:
        src = Path(path).expanduser().resolve()
        if not src.exists():
            return src
        bak = src.with_suffix(src.suffix + f".bak.{self.round_num}.{self.ticket_id}")
        if not bak.exists():
            shutil.copy2(src, bak)
            self._log({"op": "snapshot", "src": str(src), "bak": str(bak)})
        self._snapshots.append((src, bak))
        return bak

    def snapshot_many(self, paths: list[Path | str]) -> list[Path]:
        return [self.snapshot(p) for p in paths]

    def commit(self) -> None:
        self._log({"op": "commit", "count": len(self._snapshots)})

    def rollback(self) -> int:
        n = 0
        for src, bak in self._snapshots:
            if bak.exists():
                shutil.move(str(bak), str(src))
                n += 1
        self._log({"op": "rollback", "count": n})
        return n

    def _log(self, entry: dict) -> None:
        entry.update(
            {
                "ts": time.time(),
                "worker": self.worker,
                "round": self.round_num,
                "ticket_id": self.ticket_id,
            }
        )
        with self.index.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    @classmethod
    def rollback_ticket(cls, vault: Path, ticket_id: str) -> dict:
        vault = Path(vault).expanduser().resolve()
        n = 0
        for bak in vault.rglob(f"*.bak.*.{ticket_id}"):
            orig = bak.with_name(bak.name.split(".bak.")[0])
            shutil.move(str(bak), str(orig))
            n += 1
        index = vault / "meta" / ".backups.jsonl"
        if index.exists():
            with index.open("a") as f:
                f.write(json.dumps({"op": "rollback_ticket", "ticket_id": ticket_id, "count": n, "ts": time.time()}) + "\n")
        return {"rolled_back": n, "ticket_id": ticket_id}

    @classmethod
    def purge_older_than_rounds(cls, vault: Path, keep_rounds: int = 2) -> int:
        vault = Path(vault).expanduser().resolve()
        rounds = sorted(
            {int(p.name.split(".bak.")[1].split(".")[0]) for p in vault.rglob("*.bak.*.*") if ".bak." in p.name},
            reverse=True,
        )
        if len(rounds) <= keep_rounds:
            return 0
        keep_set = set(rounds[:keep_rounds])
        n = 0
        for bak in vault.rglob("*.bak.*.*"):
            try:
                r = int(bak.name.split(".bak.")[1].split(".")[0])
            except (IndexError, ValueError) as exc:
                sys.stderr.write(f"worker_backup: skipping malformed backup name {bak.name}: {type(exc).__name__}: {exc}\n")
                continue
            if r not in keep_set:
                bak.unlink()
                n += 1
        return n


def main(argv: list[str]) -> int:
    """Run the worker-backup command-line entry point."""
    if len(argv) < 3:
        sys.stderr.write("usage: worker_backup.py <vault> {rollback-ticket <id>|purge [keep_rounds]}\n")
        return 1
    vault = Path(argv[1])
    cmd = argv[2]
    if cmd == "rollback-ticket" and len(argv) > 3:
        sys.stdout.write(json.dumps(WorkerBackup.rollback_ticket(vault, argv[3]), indent=2) + "\n")
        return 0
    if cmd == "purge":
        keep = int(argv[3]) if len(argv) > 3 else 2
        n = WorkerBackup.purge_older_than_rounds(vault, keep)
        sys.stdout.write(json.dumps({"purged": n, "keep_rounds": keep}) + "\n")
        return 0
    sys.stderr.write(f"unknown cmd: {cmd}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))

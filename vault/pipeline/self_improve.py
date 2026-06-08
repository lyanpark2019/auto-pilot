#!/usr/bin/env python3
"""Schema-v2 self-improvement loop for a vault.

Reads a real-eval-style markdown report (`<vault>/meta/real-eval.md`), identifies
weak questions (below threshold), records the run in the schema-v2 learning
memory, and writes a ticket file the PM agent can pick up.

Claude-side core does NOT shell out to any LLM CLI from here — patch dispatch is
performed by the slash-command layer via the Agent tool. This module owns:

- parsing
- schema-v2 memory persistence
- weak-Q ticket emission
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO

MEMORY_VERSION = 2

DEFAULT_MEMORY_PATH = Path(os.environ.get(
    "VAULT_LEARNING_MEMORY",
    str(Path.home() / ".claude" / "memories" / "vault-builder-learning.json"),
))


def _write_line(stream: TextIO, message: str) -> None:
    stream.write(f"{message}\n")


def _emit(message: str) -> None:
    _write_line(sys.stdout, message)


def _warn(message: str) -> None:
    _write_line(sys.stderr, message)


def _default_memory() -> dict[str, Any]:
    return {
        "version": MEMORY_VERSION,
        "quality_history": [],
        "successful_patterns": [],
        "failed_approaches": [],
        "cross_project_lessons": [],
    }


def load_memory(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _default_memory()
    try:
        payload = json.loads(path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        _warn(f"self_improve: failed to load memory {path}: {type(exc).__name__}: {exc}")
        return _default_memory()
    if not isinstance(payload, dict):
        return _default_memory()
    base = _default_memory()
    base.update({k: v for k, v in payload.items() if k in base})
    if base["version"] < MEMORY_VERSION:
        base["version"] = MEMORY_VERSION
    return base


def save_memory(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def parse_real_eval_report(vault: Path) -> dict[str, float]:
    report = vault / "meta" / "real-eval.md"
    if not report.exists():
        return {}
    text = report.read_text(errors="replace")
    scores: dict[str, float] = {}
    for chunk in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        head, _, rest = chunk.partition("\n")
        task_id = head.split(" — ", 1)[0].strip()
        match = re.search(r"\*\*Score\*\*:\s*([\d.]+)\s*/\s*100", rest)
        if task_id and match:
            try:
                scores[task_id] = float(match.group(1))
            except ValueError as exc:
                _warn(f"self_improve: failed to parse score for {task_id}: {type(exc).__name__}: {exc}")
                continue
    return scores


def extract_real_eval_section(report_text: str, qid: str) -> str:
    if not report_text or not qid:
        return ""
    pattern = re.compile(rf"^## {re.escape(qid)} — .*?(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(report_text)
    return match.group(0) if match else ""


def write_weak_q_tickets(vault: Path, weak: list[str], scores: dict[str, float]) -> Path:
    """Emit `<vault>/.vault-builder/self-improve-tickets.json`.

    Each ticket lists the qid, current score, and the failing real-eval section.
    PM agent reads this and dispatches per-qid concept-page patches.
    """
    tickets_dir = vault / ".vault-builder"
    tickets_dir.mkdir(parents=True, exist_ok=True)
    report_path = vault / "meta" / "real-eval.md"
    report_text = report_path.read_text(errors="replace") if report_path.exists() else ""
    tickets = []
    for qid in weak:
        tickets.append({
            "qid": qid,
            "score": scores.get(qid, 0.0),
            "section": extract_real_eval_section(report_text, qid),
        })
    out = tickets_dir / "self-improve-tickets.json"
    out.write_text(json.dumps({
        "vault": str(vault),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickets": tickets,
    }, indent=2), encoding="utf-8")
    return out


def record_run(memory: dict[str, Any], vault: Path, scores: dict[str, float], threshold: float, weak: list[str]) -> None:
    mean = sum(scores.values()) / len(scores) if scores else 0.0
    entry = {
        "vault": str(vault),
        "vault_name": vault.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "threshold": threshold,
        "mean": round(mean, 2),
        "per_q": {q: round(s, 1) for q, s in sorted(scores.items())},
        "weak_qs": weak,
    }
    history = memory.setdefault("quality_history", [])
    if isinstance(history, list):
        history.append(entry)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="self-improve")
    parser.add_argument("vault", type=Path)
    parser.add_argument("--threshold", type=float, default=95.0)
    parser.add_argument("--memory", type=Path, default=DEFAULT_MEMORY_PATH)
    parser.add_argument("--emit-tickets", action="store_true",
                        help="write .vault-builder/self-improve-tickets.json")
    args = parser.parse_args(argv[1:])

    vault = args.vault.expanduser().resolve()
    scores = parse_real_eval_report(vault)
    if not scores:
        _warn(f"[self-improve] no real-eval report at {vault}/meta/real-eval.md")
        return 2
    mean = sum(scores.values()) / len(scores)
    weak = sorted(q for q, s in scores.items() if s < args.threshold)
    _emit(f"[self-improve] mean={mean:.2f} threshold={args.threshold} weak={weak}")

    memory_path = args.memory.expanduser().resolve()
    memory = load_memory(memory_path)
    record_run(memory, vault, scores, args.threshold, weak)
    save_memory(memory_path, memory)
    _emit(f"[self-improve] memory: {memory_path}")

    if args.emit_tickets and weak:
        ticket_path = write_weak_q_tickets(vault, weak, scores)
        _emit(f"[self-improve] tickets: {ticket_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

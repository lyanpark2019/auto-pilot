"""measure_cross_model_collect.py — live producer for the cross-model convergence measure.

Drives the REAL claude + codex reviewers over a frozen diff, K passes each, writing
``<out>/<model>/pass-N/review.json`` for ``measure_cross_model`` to analyze.

Faithful for the measured quantity — the controlled-vocab ``class`` each model picks
for a defect under the real ``review-core.md`` instruction. It deliberately does NOT
run the full ticket/contract dispatch (scope-check, verify re-run, sandbox env): none
of that affects which class a model selects, and standing up valid contracts + a git
worktree per pass would add cost and fragility for no change in the measured value.

Best-effort: a model/pass that fails to produce parseable findings is written as an
ABSTAIN review.json (the analyzer counts and tolerates it). Never aborts the batch.

CLI:
    python3 measure_cross_model_collect.py --diff <seed.diff> --out <runs> [--passes 3]
        [--models claude-reviewer codex-reviewer] [--codex-effort medium]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import codex_review_bounded as crb

_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
_REVIEW_CORE = (_PLUGIN_ROOT / "skills" / "adversarial-review-loop"
                / "references" / "review-core.md")
_CLAUDE_TIMEOUT_S = 240
_CODEX_TIMEOUT_S = 300


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_prompt(review_core: str, diff: str) -> str:
    """Reviewer prompt: the real review-core instruction + the diff + a strict output contract."""
    return (
        review_core
        + "\n\n---\n\nReview ONLY the unified diff below. For each real defect emit one "
        "finding. You MUST tag each finding with the single closest `class` from the "
        "controlled vocabulary above (omit `class` only if truly none fits).\n\n"
        "Output ONE JSON object and NOTHING else:\n"
        '{"findings":[{"file":"<path>","line":<int|null>,"severity":"P0|P1|P2",'
        '"issue":"<one line>","class":"<vocab tag>","fix":"<one line>"}]}\n\n'
        "```diff\n" + diff + "\n```\n"
    )


def _iter_json_objects(text: str) -> list[dict[str, Any]]:
    """Yield every JSON object embedded in text, string-aware.

    Uses ``json.JSONDecoder().raw_decode`` from each ``{`` so a brace inside a JSON
    string value (e.g. an ``issue`` that mentions ``{}`` or a code snippet) cannot
    desync a naive depth counter and silently drop the findings object.
    """
    dec = json.JSONDecoder()
    out: list[dict[str, Any]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == "{":
            try:
                obj, end = dec.raw_decode(text, i)
            except json.JSONDecodeError:
                i += 1
                continue
            if isinstance(obj, dict):
                out.append(obj)
                i = end
                continue
        i += 1
    return out


def extract_findings(text: str) -> list[dict[str, Any]] | None:
    """Return the findings list from the LAST JSON object that carries a findings array."""
    for obj in reversed(_iter_json_objects(text)):
        f = obj.get("findings")
        if isinstance(f, list):
            return [x for x in f if isinstance(x, dict)]
    return None


def _claude_text(raw: str) -> str:
    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(env, dict):
        res = env.get("result")
        if isinstance(res, str):
            return res
    return raw


def _codex_text(raw: str) -> str:
    """Reconstruct the assistant text from codex --json JSONL events (decoded, unescaped)."""
    chunks: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        _collect_strings(ev, chunks)
    return "\n".join(chunks) if chunks else raw


def _collect_strings(obj: Any, out: list[str]) -> None:
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_strings(v, out)


_LIMIT_PHRASES = ("usage limit", "limit reached", "rate limit", "rate limited",
                  "credit", "quota")


def _classify_msg(model: str, msg: str) -> str:
    """usage-limit vs generic exec-failed, from a failure message."""
    low = msg.lower()
    if any(p in low for p in _LIMIT_PHRASES):
        return f"{model}-usage-limit"
    return f"{model}-exec-failed"


def _fail_reason(model: str, stdout: str, stderr: str) -> str:
    """Classify a non-zero reviewer exit into an honest abstain reason.

    Distinguishes a usage-limit / credit block from a generic exec failure so the
    evidence record never mislabels a quota stop as a parse failure.
    """
    msg = ""
    for line in stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict) and ev.get("type") in ("error", "turn.failed"):
            m = ev.get("message")
            if not isinstance(m, str):
                err = ev.get("error")
                m = err.get("message") if isinstance(err, dict) else None
            if isinstance(m, str):
                msg = m
    if not msg:
        msg = stderr.strip()[-160:]
    return _classify_msg(model, msg)


def _claude_envelope_fail(raw: str) -> str | None:
    """claude -p reports a usage/error block by exiting 0 with is_error in the JSON
    envelope; classify that so a claude-side block is not mislabeled a parse failure."""
    try:
        env = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(env, dict) and env.get("is_error"):
        res = env.get("result")
        sub = env.get("subtype")
        msg = res if isinstance(res, str) else (sub if isinstance(sub, str) else "")
        return _classify_msg("claude-reviewer", msg)
    return None


def _run_claude(prompt: str) -> tuple[str, str | None]:
    proc = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=_CLAUDE_TIMEOUT_S, check=False,
    )
    if proc.returncode != 0:
        return "", _fail_reason("claude-reviewer", proc.stdout, proc.stderr)
    envelope_fail = _claude_envelope_fail(proc.stdout)
    if envelope_fail:
        return "", envelope_fail
    return _claude_text(proc.stdout), None


def _run_codex(prompt: str, effort: str) -> tuple[str, str | None]:
    proc = subprocess.run(
        crb.build_argv(effort), input=prompt,
        capture_output=True, text=True, timeout=_CODEX_TIMEOUT_S, check=False,
    )
    if proc.returncode != 0:
        return "", _fail_reason("codex-reviewer", proc.stdout, proc.stderr)
    return _codex_text(proc.stdout), None


def _finding_hash(finding: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(finding, sort_keys=True).encode()).hexdigest()


def _shape_review(model: str, findings: list[dict[str, Any]] | None,
                  abstain_reason: str | None) -> dict[str, Any]:
    """A schema-valid review.json the analyzer's read_review accepts."""
    started = _now()
    out_findings: list[dict[str, Any]] = []
    for f in findings or []:
        rec = {
            "severity": f.get("severity") if f.get("severity") in ("P0", "P1", "P2") else "P2",
            "file": str(f.get("file", "")),
            "line": f.get("line") if isinstance(f.get("line"), int) else None,
            "issue": str(f.get("issue", "")),
            "fix": str(f.get("fix", "")),
        }
        if "class" in f:
            rec["class"] = f.get("class")
        rec["finding_hash"] = _finding_hash(rec)
        out_findings.append(rec)
    meta: dict[str, Any] = {"model": model, "started_at": started, "ended_at": _now()}
    if abstain_reason:
        meta["abstain_reason"] = abstain_reason
    return {
        "schema_version": 1,
        "reviewer": model,
        "contract_id": "cross-model-measure",
        "verdict": "ABSTAIN" if abstain_reason else ("REJECT" if out_findings else "APPROVE"),
        "scope_check": "SKIPPED",
        "findings": out_findings,
        "verify_rerun": {"cmd": "n/a (measurement)", "exit_code": 0},
        "reviewer_meta": meta,
    }


def collect(diff: str, out_dir: Path, models: list[str], passes: int,
            codex_effort: str) -> dict[str, int]:
    """Run K passes per model; write review.json per pass. Returns per-model written count."""
    review_core = _REVIEW_CORE.read_text() if _REVIEW_CORE.exists() else ""
    prompt = build_prompt(review_core, diff)
    written: dict[str, int] = {}
    for model in models:
        # Clear any prior run's passes for this model so a re-run to the same --out
        # cannot leave stale pass-N dirs that the analyzer's glob would mix in.
        model_dir = out_dir / model
        if model_dir.exists():
            shutil.rmtree(model_dir)
        for p in range(1, passes + 1):
            pass_dir = out_dir / model / f"pass-{p}"
            pass_dir.mkdir(parents=True, exist_ok=True)
            findings: list[dict[str, Any]] | None = None
            reason: str | None = None
            try:
                text, reason = (_run_codex(prompt, codex_effort) if model == "codex-reviewer"
                                else _run_claude(prompt))
                if reason is None:
                    findings = extract_findings(text)
                    if findings is None:
                        reason = "no-parseable-findings"
            except subprocess.TimeoutExpired:
                reason = f"{model}-timeout"
            except FileNotFoundError:
                reason = f"{model}-not-found"
            review = _shape_review(model, findings, reason)
            (pass_dir / "review.json").write_text(
                json.dumps(review, indent=2, sort_keys=True) + "\n")
            written[model] = written.get(model, 0) + 1
            print(f"{model} pass-{p}: "
                  f"{'ABSTAIN(' + reason + ')' if reason else str(len(findings or [])) + ' finding(s)'}")
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="cross-model convergence producer")
    ap.add_argument("--diff", required=True, help="frozen seed diff to review")
    ap.add_argument("--out", required=True, help="output runs dir")
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--models", nargs="+",
                    default=["claude-reviewer", "codex-reviewer"])
    ap.add_argument("--codex-effort", default="medium")
    args = ap.parse_args(argv)
    diff = Path(args.diff).read_text()
    counts = collect(diff, Path(args.out).resolve(), args.models, args.passes,
                     args.codex_effort)
    print(json.dumps({"written": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env bash
# session-distill-stop.sh — Stop hook
#
# Advisory (non-blocking, exit 0 always): on session Stop, if this is an
# auto-pilot run (.planning/auto-pilot/state.json present under the target
# root), write ONE deterministic session-record stub page into the project's
# Obsidian vault under sessions/, linking the raw transcript.
#
# IMPORTANT: this hook has NO LLM.  It performs deterministic provenance
# capture only — frontmatter stub (project, run_id, session_id, date,
# raw-transcript link).  It does NOT distill decisions / mistakes /
# what-worked.  That distillation is delegated to the retro agent + Hermes
# miner, which carry conversation context this Stop hook does not.
#
# Once-per-session idempotency: filename = session-<safe_session_id>.md.
# Re-running for the same session overwrites the same file — never creates
# a second page.
#
# Stop-hook reentry guard: if stop_hook_active is true in the payload, exit
# immediately to avoid infinite Stop re-invocation (same idiom as
# learning-miner-stop.sh).
set -euo pipefail

payload=$(cat)

# Reentry guard — exit before any work if this Stop was triggered by a Stop hook.
if printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
sys.exit(0 if isinstance(d, dict) and d.get("stop_hook_active") is True else 1)
' 2>/dev/null; then
  exit 0
fi

# Target repo root: CLAUDE_PROJECT_DIR (repo standard) → payload cwd → $PWD.
root="${CLAUDE_PROJECT_DIR:-}"
if [[ -z "$root" ]]; then
  root=$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("cwd", "") if isinstance(d, dict) else "")
except Exception:
    print("")
' 2>/dev/null) || root=""
fi
[[ -z "$root" ]] && root="$PWD"

# Activation guard — only act on a real auto-pilot run.
[[ -f "$root/.planning/auto-pilot/state.json" ]] || exit 0

# Export payload and root for the Python block so it does not need stdin.
# All vault-path resolution and page writing is wrapped to NEVER raise.
export _SESSION_DISTILL_PAYLOAD="$payload"
export _SESSION_DISTILL_ROOT="$root"

python3 - <<'PYEOF' 2>/dev/null || true
import datetime
import json
import os
import re
import sys
import tempfile
from pathlib import Path


def _sanitize(s: str) -> str:
    """Keep [A-Za-z0-9-_], replace everything else with _."""
    return re.sub(r"[^A-Za-z0-9\-_]", "_", s)


def _yaml_scalar(s: str) -> str:
    """Strip newlines/CRs that would inject arbitrary YAML keys."""
    return s.replace("\r", " ").replace("\n", " ").strip()


def main() -> None:
    root = Path(os.environ["_SESSION_DISTILL_ROOT"]).resolve()

    tmp_path: str | None = None
    try:
        payload_raw = os.environ.get("_SESSION_DISTILL_PAYLOAD", "")
        try:
            d = json.loads(payload_raw)
        except Exception:
            d = {}

        transcript_path: str = (d.get("transcript_path") or "") if isinstance(d, dict) else ""
        session_id: str = (d.get("session_id") or "") if isinstance(d, dict) else ""

        # Normalize transcript_path to absolute (do NOT use .resolve() — it
        # canonicalizes macOS /tmp→/private/tmp symlinks and breaks test assertions).
        tp = transcript_path
        if tp:
            tp = os.path.expanduser(tp)
            if not os.path.isabs(tp):
                tp = os.path.abspath(os.path.join(str(root), tp))
        transcript_path = tp

        # Read run_id from state.json; default "unknown" on any failure.
        run_id = "unknown"
        state_file = root / ".planning" / "auto-pilot" / "state.json"
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            run_id = str(state.get("run_id") or "unknown")
        except Exception:
            pass

        # Resolve vault path: NBM_VAULT_PATH → VAULT_BUILDER_VAULT →
        # ${VB_OBSIDIAN_ROOT:-$HOME/Documents/Obsidian}/<basename(root)>
        vault_str = os.environ.get("NBM_VAULT_PATH") or os.environ.get("VAULT_BUILDER_VAULT") or ""
        if vault_str:
            vault = Path(vault_str)
        else:
            obsidian_root = Path(
                os.environ.get("VB_OBSIDIAN_ROOT")
                or str(Path.home() / "Documents" / "Obsidian")
            )
            vault = obsidian_root / root.name

        sessions_dir = vault / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        # Filename: once-per-session, idempotent.
        # Priority: session_id → run_id → "unknown".
        if session_id:
            safe_sid = _sanitize(session_id)
        elif run_id and run_id != "unknown":
            safe_sid = _sanitize(run_id)
        else:
            safe_sid = "unknown"

        page_path = sessions_dir / f"session-{safe_sid}.md"

        project = root.name
        date_str = datetime.date.today().isoformat()

        # Sanitize YAML scalars to prevent newline-based injection.
        p_project = _yaml_scalar(project)
        p_run_id = _yaml_scalar(run_id)
        p_session_id = _yaml_scalar(session_id)
        p_transcript = _yaml_scalar(transcript_path)

        content = (
            "---\n"
            f"type: session-record\n"
            f"project: {p_project}\n"
            f"run_id: {p_run_id}\n"
            f"session_id: {p_session_id}\n"
            f"date: {date_str}\n"
            f"raw_transcript: {p_transcript}\n"
            "distilled: false\n"
            "---\n"
            "\n"
            f"# Session record — {p_project} — {date_str}\n"
            "\n"
            "> Deterministic capture (no LLM). Provenance only. Decisions, mistakes, and\n"
            "> what-worked are distilled into the Hermes Ledger by the miner + retro agent,\n"
            "> which carry conversation context this Stop hook does not.\n"
            "\n"
            f"- **Project:** {p_project}\n"
            f"- **Run:** `{p_run_id}`\n"
            f"- **Session:** `{p_session_id}`\n"
            f"- **Raw transcript:** `{p_transcript}`\n"
            "\n"
            "## Distillate\n"
            "*(pending — populated by retro/miner from the Ledger)*\n"
        )
        # Atomic write: write to a temp file then os.replace (same filesystem).
        fd, tmp_path = tempfile.mkstemp(dir=sessions_dir, suffix=".md.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp_path, page_path)
            tmp_path = None  # replaced; no cleanup needed
        except Exception:
            os.close(fd)
            raise
    except Exception:
        pass
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


main()
PYEOF

exit 0

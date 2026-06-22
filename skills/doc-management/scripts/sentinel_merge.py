#!/usr/bin/env python3
"""Sentinel-aware merge for doc-management generated-mirror updates.

Sentinel convention (doc-management-system.md §sentinel):
  <!-- @generated --> ... <!-- /@generated -->   — machine-owned region
  <!-- @user -->     ... <!-- /@user -->          — human-owned region, never overwritten

merge(existing, generated) -> str:
  • If existing has no sentinels → treat whole existing doc as generated (full overwrite)
    and log once.
  • Replace every @generated region in existing with the corresponding @generated region
    from generated (matched by position order, 1-indexed).
  • Preserve every @user region byte-identical.
  • Regions absent in `generated` are left as-is in the output.

CLI:
  sentinel_merge.py <existing_path> <generated_path> [--out PATH]
  (omit --out to print to stdout)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Sentinel patterns — must stay IDENTICAL to any doc that uses them
_GEN_OPEN = "<!-- @generated -->"
_GEN_CLOSE = "<!-- /@generated -->"
_USER_OPEN = "<!-- @user -->"
_USER_CLOSE = "<!-- /@user -->"

_SENTINEL_RE = re.compile(
    r"(<!-- @generated -->.*?<!-- /@generated -->|<!-- @user -->.*?<!-- /@user -->)",
    re.DOTALL,
)


def _split_regions(text: str) -> list[tuple[str, str]]:
    """Return list of (kind, content) — kind in {'generated', 'user', 'text'}."""
    parts: list[tuple[str, str]] = []
    pos = 0
    for m in _SENTINEL_RE.finditer(text):
        if m.start() > pos:
            parts.append(("text", text[pos : m.start()]))
        block = m.group(0)
        if block.startswith(_GEN_OPEN):
            parts.append(("generated", block))
        else:
            parts.append(("user", block))
        pos = m.end()
    if pos < len(text):
        parts.append(("text", text[pos:]))
    return parts


def merge(existing: str, generated: str) -> str:
    """Merge generated doc into existing, preserving @user blocks."""
    existing_parts = _split_regions(existing)
    has_sentinels = any(k in ("generated", "user") for k, _ in existing_parts)

    if not has_sentinels:
        # No sentinels in existing → treat as full generated (caller sees this via log)
        print(
            "sentinel_merge: existing doc has no sentinels — full overwrite applied",
            file=sys.stderr,
        )
        return generated

    # Collect @generated regions from the NEW generated doc (in order)
    generated_regions = [c for k, c in _split_regions(generated) if k == "generated"]
    gen_idx = 0

    out_parts: list[str] = []
    for kind, content in existing_parts:
        if kind == "user":
            out_parts.append(content)  # byte-identical preservation
        elif kind == "generated":
            if gen_idx < len(generated_regions):
                out_parts.append(generated_regions[gen_idx])
                gen_idx += 1
            else:
                # No corresponding region in generated doc — keep existing
                out_parts.append(content)
        else:
            out_parts.append(content)

    return "".join(out_parts)


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    flags = argv[1:]

    if len(args) < 2:
        print(
            "Usage: sentinel_merge.py <existing_path> <generated_path> [--out PATH]",
            file=sys.stderr,
        )
        return 1

    existing_path = Path(args[0])
    generated_path = Path(args[1])

    out_path: Path | None = None
    for i, flag in enumerate(flags):
        if flag == "--out" and i + 1 < len(flags):
            out_path = Path(flags[i + 1])

    if not existing_path.exists():
        print(f"ERROR: existing_path not found: {existing_path}", file=sys.stderr)
        return 1
    if not generated_path.exists():
        print(f"ERROR: generated_path not found: {generated_path}", file=sys.stderr)
        return 1

    existing = existing_path.read_text(encoding="utf-8")
    generated_text = generated_path.read_text(encoding="utf-8")
    result = merge(existing, generated_text)

    if out_path:
        out_path.write_text(result, encoding="utf-8")
        print(f"sentinel_merge: wrote merged doc to {out_path}")
    else:
        sys.stdout.write(result)

    return 0


def demo() -> None:
    """Self-check: @user block preserved byte-identical; @generated replaced."""
    existing = (
        "# Doc\n\n"
        "<!-- @generated -->\nOLD generated content.\n<!-- /@generated -->\n\n"
        "<!-- @user -->\nUser note: keep this.\n<!-- /@user -->\n\n"
        "Trailing text.\n"
    )
    generated_doc = (
        "# Doc\n\n"
        "<!-- @generated -->\nNEW generated content.\n<!-- /@generated -->\n\n"
        "Trailing text.\n"
    )

    result = merge(existing, generated_doc)

    assert "NEW generated content." in result, "generated region not replaced"
    assert "OLD generated content." not in result, "old generated content persists"
    assert "User note: keep this." in result, "@user block not preserved"
    assert _USER_OPEN in result and _USER_CLOSE in result, "@user sentinels stripped"

    # No-sentinel case → full overwrite
    plain_existing = "# Plain doc\n\nOld prose.\n"
    result2 = merge(plain_existing, "# Plain doc\n\nNew prose.\n")
    assert result2 == "# Plain doc\n\nNew prose.\n", "no-sentinel overwrite failed"

    print("sentinel_merge demo: all assertions passed")


if __name__ == "__main__":
    if "--demo" in sys.argv or (len(sys.argv) == 1 and sys.argv[0].endswith("sentinel_merge.py")):
        demo()
        sys.exit(0)
    sys.exit(main(sys.argv))

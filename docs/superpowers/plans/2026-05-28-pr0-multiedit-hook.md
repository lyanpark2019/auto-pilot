# PR0 — MultiEdit Hook Matcher Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close composition-root guard bypass when worker uses MultiEdit instead of Edit/Write.

**Architecture:** Single-line matcher change in `hooks/hooks.json` + smoke test. Orthogonal to PR1/PR2/PR3.

**Tech Stack:** bash, JSON, pytest subprocess fixtures.

---

## Task 1: MultiEdit hook matcher

**Files:**
- Modify: `hooks/hooks.json` (the `Edit|Write` matcher for `pre-edit-composition-root.sh`)
- Modify: `tests/test_hooks.py` (add MultiEdit case to existing composition-root hook test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_hooks.py`:

```python
def test_pre_edit_composition_root_blocks_multiedit(plugin_root):
    """MultiEdit to __init__.py must be blocked, same as Edit/Write."""
    hook = plugin_root / "hooks" / "pre-edit-composition-root.sh"
    tool_input = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": "/abs/path/to/pkg/__init__.py",
            "edits": [{"old_string": "a", "new_string": "b"}],
        },
    }
    result = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(tool_input),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, f"expected exit 2, got {result.returncode}: {result.stderr}"
    assert "BLOCKED" in result.stderr
```

- [ ] **Step 2: Run test to verify it fails (hook script reads `file_path` regardless of tool_name, so the script itself will pass — failure must come from the matcher in `hooks.json` not firing)**

Actually re-check: `pre-edit-composition-root.sh` extracts `tool_input.file_path` and blocks regardless of `tool_name`. So the SCRIPT already blocks MultiEdit when invoked directly. The real bug is that `hooks/hooks.json` matcher `"Edit|Write"` never INVOKES the script for MultiEdit tool calls.

So the test above will PASS even before the fix (because it bypasses the matcher and calls the script directly). The real test must verify the registration in `hooks.json`:

Replace the test with:

```python
def test_hooks_json_matcher_includes_multiedit():
    """hooks.json PreToolUse matcher for composition-root hook must cover MultiEdit."""
    import json as _json
    from pathlib import Path
    hooks_json = Path(__file__).parent.parent / "hooks" / "hooks.json"
    data = _json.loads(hooks_json.read_text())
    pre_tool_use = data["hooks"]["PreToolUse"]
    composition_root_entry = next(
        e for e in pre_tool_use
        if any("pre-edit-composition-root.sh" in h["command"] for h in e["hooks"])
    )
    matcher = composition_root_entry["matcher"]
    for tool in ("Edit", "Write", "MultiEdit"):
        assert tool in matcher.split("|"), f"matcher {matcher!r} missing {tool}"
```

Run: `pytest tests/test_hooks.py::test_hooks_json_matcher_includes_multiedit -v`
Expected: FAIL with `AssertionError: matcher 'Edit|Write' missing MultiEdit`

- [ ] **Step 3: Fix `hooks/hooks.json`**

Locate the entry:

```json
{
  "matcher": "Edit|Write",
  "hooks": [
    {
      "type": "command",
      "command": "${CLAUDE_PLUGIN_ROOT}/hooks/pre-edit-composition-root.sh"
    }
  ]
}
```

Change `"Edit|Write"` to `"Edit|Write|MultiEdit"`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hooks.py::test_hooks_json_matcher_includes_multiedit -v`
Expected: PASS

- [ ] **Step 5: Also add a direct-invocation smoke test for the hook script with MultiEdit input shape**

Append to `tests/test_hooks.py`:

```python
def test_pre_edit_composition_root_handles_multiedit_input_shape():
    """When invoked via the matcher, script must extract file_path from MultiEdit input."""
    from pathlib import Path
    hook = Path(__file__).parent.parent / "hooks" / "pre-edit-composition-root.sh"
    tool_input = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_path": "/tmp/some/pkg/__init__.py",
            "edits": [{"old_string": "x", "new_string": "y"}],
        },
    }
    result = subprocess.run(
        ["bash", str(hook)],
        input=json.dumps(tool_input),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "BLOCKED" in result.stderr
```

Run: `pytest tests/test_hooks.py::test_pre_edit_composition_root_handles_multiedit_input_shape -v`
Expected: PASS (hook script already reads `tool_input.file_path` regardless of tool_name)

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add hooks/hooks.json tests/test_hooks.py
git commit -m "$(cat <<'EOF'
fix(hooks): include MultiEdit in composition-root guard matcher

The PreToolUse matcher for pre-edit-composition-root.sh covered only
Edit and Write, leaving MultiEdit as a free bypass. Worker dispatching
MultiEdit on __init__.py would never trigger the block.

Test asserts hooks.json matcher contains MultiEdit + direct-invocation
smoke confirms the script handles MultiEdit input shape correctly.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Done

PR0 is one commit. Push branch, open PR, merge. PR1/PR2/PR3 do not depend on this.

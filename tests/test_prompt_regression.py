"""Regression suite for prompts/ — fixture-driven, >=10 cases covering iteration + headless prompts.

Each fixture under prompts/fixtures/*.json declares:
  - prompt: name passed to _prompts.load() or _prompts.render()
  - call:  "load" or "render" (default "render"); pick "load" for static
           prompts that contain literal `${...}` shell syntax that would
           confuse `str.format_map`
  - vars:  kwargs for render (ignored when call == "load")
  - expects_substring: list of literal substrings the output MUST contain
  - expects_not:        list of literal substrings the output MUST NOT contain
                        (catches un-resolved {placeholder} leaks, ignored extras)

No full-text snapshotting — too brittle to whitespace tweaks. Substring asserts
catch the load-bearing facts (placeholder resolution, commit-trailer markers,
HEADLESS preamble, failure-clause presence) without churning on every edit.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import _prompts  # type: ignore[import-not-found]

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "prompts" / "fixtures"


def _all_fixtures() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


def test_fixtures_directory_has_minimum_cases():
    cases = _all_fixtures()
    assert len(cases) >= 10, (
        f"prompt regression suite needs >=10 fixtures, found {len(cases)}"
    )


@pytest.mark.parametrize("fixture_path", _all_fixtures(), ids=lambda p: p.stem)
def test_fixture_render_matches_expectations(fixture_path: Path) -> None:
    case = json.loads(fixture_path.read_text())
    prompt = case["prompt"]
    vars_ = case.get("vars", {})
    call = case.get("call", "render")
    if call == "load":
        rendered = _prompts.load(prompt)
    elif call == "render":
        rendered = _prompts.render(prompt, **vars_)
    else:
        raise ValueError(f"{fixture_path.name}: unknown call {call!r}")
    for sub in case.get("expects_substring", []):
        assert sub in rendered, (
            f"{fixture_path.name}: expected substring not found: {sub!r}\n"
            f"---rendered---\n{rendered}"
        )
    for sub in case.get("expects_not", []):
        assert sub not in rendered, (
            f"{fixture_path.name}: forbidden substring present: {sub!r}\n"
            f"---rendered---\n{rendered}"
        )


def test_iteration_prompt_has_commit_trailer_markers() -> None:
    """Downstream loop parses commits for these literal trailer keys."""
    rendered = _prompts.render("iteration", iter_n=1, phase=1)
    assert "auto-pilot-iter:" in rendered
    assert "auto-pilot-phase:" in rendered


def test_extra_vars_do_not_crash_render() -> None:
    """str.format_map silently ignores unused keys — verify, lock in the contract."""
    out = _prompts.render("iteration", iter_n=1, phase=1, unused_extra="ignore_me")
    assert "Iteration 1" in out
    assert "ignore_me" not in out


def test_headless_render_raises_keyerror() -> None:
    """Headless contains literal `${HARNESS_HEADLESS:-0}` shell syntax.
    `str.format_map` parses `{HARNESS_HEADLESS:-0}` as a Python field and
    raises KeyError — callers must use `_prompts.load("headless")`.
    """
    with pytest.raises(KeyError):
        _prompts.render("headless")

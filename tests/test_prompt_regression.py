"""Regression suite for prompts/ — fixture-driven, >=10 cases covering iteration + headless prompts.

Each fixture under prompts/fixtures/*.json declares:
  - prompt: name passed to _prompts.render()
  - vars:  kwargs (may be empty)
  - expects_substring: list of literal substrings the render MUST contain
  - expects_not:        list of literal substrings the render MUST NOT contain
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
    rendered = _prompts.render(prompt, **vars_)
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


def test_headless_render_no_vars_equals_load() -> None:
    """Idempotency: headless contains literal `${...}` shell syntax, so the
    no-vars short-circuit in _prompts.render must return the raw file untouched.
    """
    assert _prompts.render("headless") == _prompts.load("headless")

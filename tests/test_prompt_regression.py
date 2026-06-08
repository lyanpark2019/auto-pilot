"""Regression suite for prompts/ — fixture-driven, >=20 cases covering iteration + headless prompts.

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
import jsonschema

import _prompts  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "prompts" / "fixtures"
PROMPT_FIXTURE_SCHEMA = ROOT / "schemas" / "prompt-fixture.schema.json"


def _all_fixtures() -> list[Path]:
    return sorted(FIXTURES_DIR.glob("*.json"))


def test_fixtures_directory_has_minimum_cases():
    cases = _all_fixtures()
    assert len(cases) >= 20, (
        f"prompt regression suite needs >=20 fixtures, found {len(cases)}"
    )


def test_prompt_fixture_schema_is_valid_jsonschema() -> None:
    jsonschema.Draft202012Validator.check_schema(json.loads(PROMPT_FIXTURE_SCHEMA.read_text()))


@pytest.mark.parametrize("fixture_path", _all_fixtures(), ids=lambda p: p.stem)
def test_fixture_shape_matches_schema(fixture_path: Path) -> None:
    schema = json.loads(PROMPT_FIXTURE_SCHEMA.read_text())
    jsonschema.Draft202012Validator(schema).validate(json.loads(fixture_path.read_text()))


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


def test_prompt_regression_has_adversarial_fixture_set() -> None:
    adversarial = [
        json.loads(path.read_text()).get("adversarial", False)
        for path in _all_fixtures()
    ]

    assert sum(1 for value in adversarial if value) >= 5


@pytest.mark.parametrize(
    "fixture_name",
    [
        "08-iteration-prompt-injection.json",
        "14-iteration-unicode-confusables.json",
        "15-iteration-control-chars-ansi.json",
        "18-iteration-markdown-breaking.json",
        "19-iteration-json-in-var.json",
    ],
)
def test_named_adversarial_prompt_fixture_exists(fixture_name: str) -> None:
    data = json.loads((FIXTURES_DIR / fixture_name).read_text())

    assert data["adversarial"] is True


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


def test_render_for_llm_redacts_secret_like_prompt_output() -> None:
    rendered = _prompts.render_for_llm(
        "iteration",
        iter_n="api_key=sk-live-secret-token-123456",
        phase=1,
    )

    assert "sk-live-secret-token-123456" not in rendered
    assert "api_key=<redacted>" in rendered


def test_render_for_llm_strips_ansi_and_control_chars() -> None:
    rendered = _prompts.render_for_llm("iteration", iter_n="\x1b[31m5\x00", phase=1)

    assert "\x1b" not in rendered
    assert "\x00" not in rendered
    assert "Iteration 5" in rendered


def test_render_for_llm_enforces_prompt_budget() -> None:
    with pytest.raises(_prompts.PromptBudgetError):
        _prompts.render_for_llm("iteration", iter_n="x" * 2_000, phase=1, max_chars=500)

from __future__ import annotations

import _prompts


def test_load_headless_returns_text():
    text = _prompts.load("headless")
    assert text.strip()
    assert "HEADLESS MODE" in text  # known content from preamble


def test_load_iteration_has_placeholders():
    text = _prompts.load("iteration")
    assert "{iter_n}" in text
    assert "{phase}" in text


def test_render_iteration_resolves_placeholders():
    rendered = _prompts.render("iteration", iter_n=7, phase=3)
    assert "Iteration 7" in rendered
    assert "phase 3" in rendered
    assert "{iter_n}" not in rendered
    assert "{phase}" not in rendered


def test_render_iteration_without_vars_raises():
    """Safety contract: if caller forgets vars, fail loud — do not silently
    return a template with `{iter_n}`/`{phase}` leaking to the LLM."""
    import pytest

    with pytest.raises(KeyError):
        _prompts.render("iteration")


def test_render_headless_must_use_load():
    """The headless preamble contains literal `${HARNESS_HEADLESS:-0}`
    which `format_map` parses as a Python field and raises KeyError.
    Callers must use `load("headless")`, not `render`."""
    import pytest

    with pytest.raises(KeyError):
        _prompts.render("headless")

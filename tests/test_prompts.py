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


def test_render_headless_with_no_vars_is_load():
    assert _prompts.render("headless") == _prompts.load("headless")

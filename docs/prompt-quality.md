---
type: reference
topic: auto-pilot-prompt-quality
---

# auto-pilot prompt quality gates

Prompt templates are durable assets. The codebase keeps the template layer simple
and puts LLM-call safety at the call boundary.

## Template layer

- `scripts/_prompts.py::load()` returns raw prompt text from `prompts/*.md`.
- `scripts/_prompts.py::render()` only resolves `{placeholder}` values.
- `render()` intentionally does not sanitize, truncate, normalize, or escape
  template vars. The fixture suite locks this in so prompt regressions are
  visible instead of silently masked.

## LLM call boundary

Use `scripts/_prompts.py::render_for_llm()` or `sanitize_for_llm()` before a
rendered prompt is sent to an LLM process. That boundary enforces:

- secret-like assignment redaction (`api_key=...`, `token=...`, `password=...`),
- quoted and JSON-shaped secret field redaction (`token="..."`, `"api_key": "..."`),
- bearer/OpenAI-style key redaction (`Authorization: Bearer ...`, raw `sk-...`),
- ANSI escape and non-printing control-character removal,
- a rendered-output size cap (`MAX_LLM_PROMPT_CHARS`).

`headless-loop.py` applies this boundary before spawning Claude, so the prompt
output path is guarded even if a future caller passes hostile prompt text.

## Regression evidence

- `tests/test_prompt_regression.py` validates every fixture against
  `schemas/prompt-fixture.schema.json`.
- The fixture set must keep at least 20 cases and at least 5 adversarial cases.
- Safe-render tests verify redaction, control-character scrubbing, and prompt
  budget enforcement.
- `tests/test_headless_loop_cli.py` verifies the final subprocess prompt is
  sanitized before spawn.

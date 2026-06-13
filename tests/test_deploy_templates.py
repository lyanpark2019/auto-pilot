from __future__ import annotations

from pathlib import Path

import pytest
import yaml

TEMPLATES = sorted(Path("deploy/templates").glob("*.yml"))


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_parses_as_yaml(template: Path) -> None:
    result = yaml.safe_load(template.read_text(encoding="utf-8"))
    assert isinstance(result, dict)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_no_stale_action_pins(template: Path) -> None:
    text = template.read_text(encoding="utf-8")
    assert "actions/checkout@v4" not in text
    assert "actions/setup-node@v4" not in text
    assert "actions/setup-node@v5" not in text


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_template_pins_match_policy(template: Path) -> None:
    text = template.read_text(encoding="utf-8")
    assert "actions/checkout@v5" in text
    if "actions/setup-node@" in text:
        assert "actions/setup-node@v6" in text


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_every_uses_step_is_version_pinned(template: Path) -> None:
    data = yaml.safe_load(template.read_text(encoding="utf-8"))
    # 'on:' is parsed as bool True under YAML 1.1 — walk jobs only
    for job in data["jobs"].values():
        for step in job.get("steps", []):
            if "uses" in step:
                assert "@" in step["uses"], f"unpinned action: {step['uses']!r}"

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_VERSION = "0.8.7"
EXPECTED_STATE = "RELEASED_V0_8_7"
EXPECTED_COMMIT = "e3200cb2b730c9bca60b57ca0a92ccd3d3ddb8bb"
EXPECTED_CI_RUN = 27138414829
EXPECTED_RELEASE_URL = "https://github.com/lyanpark2019/auto-pilot/releases/tag/v0.8.7"


def _load_json(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text())


def test_v087_release_state_matches_plugin_manifests() -> None:
    plugin = _load_json(".claude-plugin/plugin.json")
    marketplace = _load_json(".claude-plugin/marketplace.json")
    state = _load_json(".planning/quality/score-state.json")

    marketplace_plugins = marketplace["plugins"]
    assert isinstance(marketplace_plugins, list)
    marketplace_plugin = marketplace_plugins[0]
    assert isinstance(marketplace_plugin, dict)
    assert plugin["version"] == EXPECTED_VERSION
    assert marketplace_plugin["version"] == EXPECTED_VERSION

    assert state["current_state"] == EXPECTED_STATE
    assert state["head_sha"] == EXPECTED_COMMIT

    release = state.get("release")
    assert isinstance(release, dict)
    assert release["tag"] == f"v{EXPECTED_VERSION}"
    assert release["commit"] == EXPECTED_COMMIT
    assert release["ci_run"] == EXPECTED_CI_RUN
    assert release["url"] == EXPECTED_RELEASE_URL
    assert release["plugin_version"] == EXPECTED_VERSION

    release_status_text = json.dumps(
        [state.get("decision", ""), state.get("residual_risks", [])]
    ).lower()
    forbidden_fragments = ("pending", "blocked", "release remains blocked")
    assert not any(fragment in release_status_text for fragment in forbidden_fragments)

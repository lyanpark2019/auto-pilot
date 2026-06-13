from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPECTED_VERSION = "0.8.9"
EXPECTED_COMMIT = "8c4a3916ac0bc182204d7f8b1a6a492477bdcba2"
EXPECTED_CI_RUN = 27466105529
EXPECTED_RELEASE_URL = "https://github.com/lyanpark2019/auto-pilot/releases/tag/v0.8.9"


def _load_json(path: str) -> dict[str, object]:
    return json.loads((ROOT / path).read_text())


def _marketplace_plugin(marketplace: dict[str, object]) -> dict[str, object]:
    plugins = marketplace["plugins"]
    assert isinstance(plugins, list)
    plugin = plugins[0]
    assert isinstance(plugin, dict)
    return plugin


def _released_state_for(version: str) -> str:
    return "RELEASED_V" + version.replace(".", "_")


def _assert_release_state_consistency(
    plugin: dict[str, object], marketplace: dict[str, object], state: dict[str, object]
) -> None:
    version = plugin["version"]
    assert isinstance(version, str)
    marketplace_plugin = _marketplace_plugin(marketplace)
    assert marketplace_plugin["version"] == version

    assert state["current_state"] == _released_state_for(version)
    release = state.get("release")
    assert isinstance(release, dict)
    assert release["tag"] == f"v{version}"
    assert release["plugin_version"] == version
    assert release["marketplace_version"] == version

    release_status_text = json.dumps(
        [state.get("decision", ""), state.get("residual_risks", [])]
    ).lower()
    forbidden_fragments = ("pending", "blocked", "release remains blocked")
    assert not any(fragment in release_status_text for fragment in forbidden_fragments)


def test_release_state_invariant_derives_version_from_manifest() -> None:
    plugin = _load_json(".claude-plugin/plugin.json")
    marketplace = _load_json(".claude-plugin/marketplace.json")
    state = _load_json(".planning/quality/score-state.json")

    next_plugin = deepcopy(plugin)
    next_marketplace = deepcopy(marketplace)
    next_state = deepcopy(state)

    next_plugin["version"] = "0.9.9"
    marketplace_plugin = _marketplace_plugin(next_marketplace)
    marketplace_plugin["version"] = "0.9.9"

    release = next_state["release"]
    assert isinstance(release, dict)
    release["tag"] = "v0.9.9"
    release["plugin_version"] = "0.9.9"
    release["marketplace_version"] = "0.9.9"
    next_state["current_state"] = "RELEASED_V0_9_9"

    _assert_release_state_consistency(next_plugin, next_marketplace, next_state)


def test_current_release_state_matches_plugin_manifests() -> None:
    plugin = _load_json(".claude-plugin/plugin.json")
    marketplace = _load_json(".claude-plugin/marketplace.json")
    state = _load_json(".planning/quality/score-state.json")

    _assert_release_state_consistency(plugin, marketplace, state)
    assert plugin["version"] == EXPECTED_VERSION
    assert state["head_sha"] == EXPECTED_COMMIT

    release = state.get("release")
    assert isinstance(release, dict)
    assert release["commit"] == EXPECTED_COMMIT
    assert release["ci_run"] == EXPECTED_CI_RUN
    assert release["url"] == EXPECTED_RELEASE_URL

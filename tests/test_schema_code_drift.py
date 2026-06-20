"""Drift guards for code mirrors that are NOT enforced by a schema at runtime.

Each test pins a Python (or shell) constant to its mirror so manual edits to one
side without the other fail in CI:

  (a) ``_dispatch._VALID_ROLES``  vs  schemas/ticket.schema.json subagent_role enum
  (b) the gh-auth owner→user table duplicated in hooks/gh-auth-preflight.sh and
      scripts/pm_preflight.sh (the hook comment admits "SoT mirror").
  (e) ``_escalation.TRANSITIONS``  vs  escalation-record.schema.json state enum
  (f) ``_escalation._PROBLEM_CLASS_CHOICES``  vs  problem_class enum
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import _dispatch  # noqa: E402  (sys.path set above)
import _escalation  # noqa: E402


# ── (a) _VALID_ROLES ⇄ ticket.schema.json subagent_role enum ──────────────────


def test_valid_roles_matches_ticket_schema_enum() -> None:
    """_dispatch._VALID_ROLES must equal the subagent_role enum verbatim.

    prepare_subagent_ticket() rejects roles outside _VALID_ROLES *and* the
    written ticket is schema-validated against subagent_role's enum. If the two
    drift, a role accepted by one layer is rejected by the other.
    """
    schema_path = REPO_ROOT / "schemas" / "ticket.schema.json"
    schema = json.loads(schema_path.read_text())
    enum = schema["properties"]["subagent_role"]["enum"]
    schema_roles = {e for e in enum if isinstance(e, str)}
    code_roles = set(_dispatch._VALID_ROLES)

    only_code = code_roles - schema_roles
    only_schema = schema_roles - code_roles
    assert code_roles == schema_roles, (
        "subagent_role drift between _dispatch._VALID_ROLES and "
        f"{schema_path.relative_to(REPO_ROOT)} subagent_role enum: "
        f"in code-not-schema={sorted(only_code)}, "
        f"in schema-not-code={sorted(only_schema)}"
    )


# ── (b) gh-auth owner→user table: hook ⇄ pm_preflight.sh ──────────────────────

# The shell sources express the SAME owner→user map two different ways:
#   hook (gh-auth-preflight.sh):  case "$owner" in  Sewhoan) expected_user="Sewhoan" ;;
#   pm_preflight.sh:              if echo "$url" | grep -qE '...Sewhoan/'; then echo "Sewhoan"
# Rather than fully parse two shell dialects, assert that for each KNOWN owner
# both files resolve to the same user string. This catches manual-maintenance
# drift (the failure mode the audit flagged) without brittle full-shell parsing.
_KNOWN_OWNERS = ("Sewhoan", "lyanpark2019")

_HOOK_PATH = REPO_ROOT / "hooks" / "gh-auth-preflight.sh"
_PREFLIGHT_PATH = REPO_ROOT / "scripts" / "pm_preflight.sh"


def _hook_owner_map(text: str) -> dict[str, str]:
    """Parse the `case "$owner" in  <owner>) expected_user="<user>" ;;` arms."""
    out: dict[str, str] = {}
    pattern = re.compile(
        r'^\s*([A-Za-z0-9_-]+)\)\s*expected_user="([^"]+)"\s*;;', re.MULTILINE
    )
    for owner, user in pattern.findall(text):
        out[owner] = user
    return out


def _preflight_owner_map(text: str) -> dict[str, str]:
    """Parse the `if echo "$url" | grep -qE '...<owner>/'; then echo "<user>"` rules."""
    out: dict[str, str] = {}
    pattern = re.compile(
        r"github\\\.com\[:/\]\)" + r"([A-Za-z0-9_-]+)/'"
        r".*?echo\s+\"([^\"]+)\"",
        re.DOTALL,
    )
    for owner, user in pattern.findall(text):
        out[owner] = user
    return out


def test_gh_auth_owner_user_maps_identical() -> None:
    """The owner→user mapping must be identical in both shell files (SoT mirror)."""
    hook_map = _hook_owner_map(_HOOK_PATH.read_text())
    preflight_map = _preflight_owner_map(_PREFLIGHT_PATH.read_text())

    # Sanity: each parser must have actually matched the known owners, else a
    # silently-empty map would make the equality assert pass vacuously.
    for owner in _KNOWN_OWNERS:
        assert owner in hook_map, (
            f"parser failed to find owner {owner!r} in "
            f"{_HOOK_PATH.relative_to(REPO_ROOT)} — fix the regex, do not skip"
        )
        assert owner in preflight_map, (
            f"parser failed to find owner {owner!r} in "
            f"{_PREFLIGHT_PATH.relative_to(REPO_ROOT)} — fix the regex, do not skip"
        )

    for owner in _KNOWN_OWNERS:
        assert hook_map[owner] == preflight_map[owner], (
            f"gh-auth owner→user DRIFT for owner {owner!r}: "
            f"{_HOOK_PATH.relative_to(REPO_ROOT)} maps it to "
            f"{hook_map[owner]!r} but "
            f"{_PREFLIGHT_PATH.relative_to(REPO_ROOT)} maps it to "
            f"{preflight_map[owner]!r}"
        )


def test_gh_auth_known_owners_self_mapped() -> None:
    """Defense in depth: both files map each known owner to its own name.

    Decouples the drift check from the (correct-today) identity convention so a
    future divergence is caught even if both files drift together to the same
    wrong value.
    """
    hook_map = _hook_owner_map(_HOOK_PATH.read_text())
    preflight_map = _preflight_owner_map(_PREFLIGHT_PATH.read_text())
    for owner in _KNOWN_OWNERS:
        assert hook_map.get(owner) == owner, (
            f"{_HOOK_PATH.relative_to(REPO_ROOT)}: owner {owner!r} should map to "
            f"itself, got {hook_map.get(owner)!r}"
        )
        assert preflight_map.get(owner) == owner, (
            f"{_PREFLIGHT_PATH.relative_to(REPO_ROOT)}: owner {owner!r} should map "
            f"to itself, got {preflight_map.get(owner)!r}"
        )


# ── (e) _escalation.TRANSITIONS keys == escalation-record.schema.json state enum ─

_ESCALATION_SCHEMA_PATH = REPO_ROOT / "schemas" / "escalation-record.schema.json"


def test_escalation_transitions_keys_match_schema_state_enum() -> None:
    """_escalation.TRANSITIONS keys must equal the escalation schema state enum exactly.

    A state present in TRANSITIONS but absent from the schema (or vice versa) means
    a record in that state would fail validation or FSM lookup.
    """
    schema = json.loads(_ESCALATION_SCHEMA_PATH.read_text())
    schema_states = set(schema["properties"]["state"]["enum"])
    code_states = set(_escalation.TRANSITIONS.keys())

    only_code = code_states - schema_states
    only_schema = schema_states - code_states
    assert code_states == schema_states, (
        f"TRANSITIONS/state enum drift: "
        f"in code-not-schema={sorted(only_code)}, "
        f"in schema-not-code={sorted(only_schema)}"
    )


# ── (f) _escalation._PROBLEM_CLASS_CHOICES == escalation-record.schema.json problem_class enum ─


def test_escalation_problem_class_choices_match_schema_enum() -> None:
    """_escalation._PROBLEM_CLASS_CHOICES must equal the schema problem_class enum exactly.

    A choice accepted by the CLI but absent from the schema (or vice versa) means
    a record created via the CLI would fail validation.
    """
    schema = json.loads(_ESCALATION_SCHEMA_PATH.read_text())
    schema_classes = set(schema["properties"]["problem_class"]["enum"])
    code_classes = set(_escalation._PROBLEM_CLASS_CHOICES)

    only_code = code_classes - schema_classes
    only_schema = schema_classes - code_classes
    assert code_classes == schema_classes, (
        f"_PROBLEM_CLASS_CHOICES/problem_class enum drift: "
        f"in code-not-schema={sorted(only_code)}, "
        f"in schema-not-code={sorted(only_schema)}"
    )

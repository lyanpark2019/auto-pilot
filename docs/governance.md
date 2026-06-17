---
topic: governance-policy-map
owner: hooks/hooks.json
---

# Governance map

> Single index of every policy the loop enforces. Framing borrowed from omnigent's
> "policies as one scoped layer" — auto-pilot already enforces each axis, but across
> separate modules + hooks; this page is the one map. **Index only — it cites, it
> does not restate.** Source of truth = the cited code + `docs/architecture.md`.

Every axis is **code-enforced** (hook / schema / module), per principle #2
"enforce with code, not prompts". This page only points. Symbol names are plain
text, not code-spans, so the doc-ref guard couples each cite to its own line only.

**Budget caps** — cost / token / pid / wall-clock per headless run.
- `scripts/_budget.py:187` — check_caps entry point
- `scripts/_budget.py:148` — check_wall_clock deadline

**Model routing** — tier→model, codex effort by risk, verifier tier floor.
- `skills/auto-pilot/references/model-routing.yaml:49` — effort_by_risk_tier
- `skills/auto-pilot/references/model-routing.yaml:36` — verifier_min_tier floor
- gate: hooks/verifier-tier-gate.sh

**Risk → review policy** — single vs dual vs +gatekeeper, per diff risk tier.
- `scripts/risk_assess.py:61` — REVIEW_POLICY map

**Reviewer sandbox** — reviewers read-only via 3 independent walls.
- frontmatter tools whitelist + hooks/pre-reviewer-write.sh + PM assert_reviewer_was_scoped post-check (architecture.md "Reviewer sandbox")

**Worker scope** — worker edits ⊆ contract scope_files.
- hooks/worker-scope-gate.sh

**Escalation** — tier-1 give-up → tier-2 bounded retry / abandon.
- `scripts/_escalation.py:172` — bump_or_create
- `scripts/_escalation.py:238` — record_resolution
- agent: agents/escalation-resolver.md

**Learnings inject gate** — worker dispatch DENIED unless gate-passed learnings resolved.
- `scripts/_learnings.py:40` — is_gate_passed predicate
- `hooks/dispatch-contract-gate.sh:205` — worker-ticket presence check

**State writes** — state.json only via lock+atomic; root tree only via apply_to_main.
- hooks/state-write-guard.sh

**Interception substrate:** every PreToolUse / Stop / SubagentStop guard is wired
in `hooks/hooks.json` — the registry SoT and auto-pilot's equivalent of omnigent's
policy table: one place, scoped by tool + subagent role (`AUTO_PILOT_SUBAGENT_ROLE`).

## Not borrowed from omnigent (explicit non-goals)

auto-pilot is a single-user local plugin. omnigent's device-sync, web/mobile UI,
live co-drive, cloud disposable sandboxes (Modal/Daytona), and YAML-swappable
harness are **N/A** — no porting. The cross-vendor review + model routing + budget
+ escalation that omnigent generalizes are this loop's existing vertical, already
shipped above.

See also: `docs/architecture.md`, `docs/configuration.md`, `CLAUDE.md`.

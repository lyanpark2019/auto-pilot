# ADR-NNNN: {Title}

Date: {YYYY-MM-DD}
Status: Proposed | Accepted | Superseded by [ADR-MMMM](MMMM-title.md) | Deprecated

## Context

What is the issue we're seeing that motivates this decision? Include only facts.

## Decision

What is the change we're making? One paragraph, declarative.

## Consequences

What becomes easier? What becomes harder? Trade-offs accepted.

## Enforcement

How is this decision enforced mechanically (not by prose)?

- Linter rule: `{rule_id}` in `{config_file}`
- Hook: `.claude/scripts/{hook_name}.sh`
- Test: `{test_path}`

If enforcement is by prose only, this ADR is not finished — find a mechanical enforcement first.

## References

- {PR/issue/incident link}
- {paper/blog link}

---

**For the agent**: this ADR is immutable. To change the decision, create ADR-{NNNN+1} that supersedes this one and update the `Status` field to point to the new ADR. Never edit the body once the status is `Accepted`.

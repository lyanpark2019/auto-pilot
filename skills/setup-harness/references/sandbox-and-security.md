# Sandbox + security setup

Layered defense based on Trail of Bits + Lasso Security + Anthropic Constitutional Classifiers research.

## Threat model

| Attack surface | Concrete risk |
|---------------|---------------|
| **Prompt injection via external content** | Malicious instructions in READMEs, fetched pages, MCP server responses, package descriptions. Claude follows instructions found in content. |
| **Supply chain via `.claude/`** | Cloned repo ships hostile hooks, MCP configs, CLAUDE.md with hidden directives. |
| **Credential exposure** | `.env`, SSH keys, AWS creds read and accidentally leaked in outputs, logs, tool calls. |
| **Side-channel via observability** | hooks logging full prompts may leak credentials to disk. |

## Layered defense

| Layer | Mechanism | Limitation |
|-------|-----------|------------|
| 1. Permission deny | `settings.json` `permissions.deny` blocks Read/Edit on `.env`, `~/.ssh/`, `~/.aws/` | Bash bypasses |
| 2. PreToolUse Bash hooks | `guard-bash.sh` — regex block `rm -rf`, `git push --force`, `curl \| bash`, `--no-verify`, `git add -A` | Pattern, not semantic |
| 3. OS sandbox | `/sandbox` per-session (macOS Seatbelt / Linux bubblewrap) | Must enable each session |
| 4. UserPromptSubmit secret scan | `scan-secrets.sh` — regex AWS/GH/Anthropic/OpenAI/PEM/BIP39 | Novel formats miss |
| 5. PostToolUse injection defender | `injection-defender.sh` — scan Read/WebFetch/Bash output for "ignore previous", "you are now" | Pattern-based |
| 6. CLAUDE.md natural-language rules | Rules with reasons | Not enforcement |

Single most important: **`/sandbox` per session**. On macOS uses Seatbelt; on Linux uses bubblewrap. Prevents bash from bypassing settings.json deny rules.

## Global settings hardening

In your `~/.claude/settings.json`:

```json
{
  "enableAllProjectMcpServers": false,
  "permissions": {
    "deny": [
      "Read(~/.ssh/**)",
      "Read(~/.aws/credentials)",
      "Read(~/.aws/config)",
      "Read(~/.gnupg/**)",
      "Read(~/.docker/config.json)",
      "Read(~/.kube/config)",
      "Read(~/.netrc)",
      "Edit(~/.bashrc)",
      "Edit(~/.zshrc)",
      "Edit(~/.profile)",
      "Edit(~/.gitconfig)",
      "Edit(~/.ssh/**)"
    ]
  }
}
```

## Cloning unknown repos

Most dangerous scenario. Before opening with Claude Code:

```bash
# 1. Audit any .claude/ infra in the repo
find . -path ./node_modules -prune -o -name 'settings.json' -print 2>/dev/null | grep '\.claude/'
find . -path ./node_modules -prune -o -name 'settings.local.json' -print 2>/dev/null | grep '\.claude/'
find . -path ./node_modules -prune -o -name '*.sh' -print 2>/dev/null | grep '\.claude/'

# 2. Audit MCP config
[ -f .mcp.json ] && jq '.' .mcp.json

# 3. Check CLAUDE.md for hidden directives
[ -f CLAUDE.md ] && cat CLAUDE.md
```

Look for:
- Hooks calling `curl | bash` or piping network content
- MCP servers pointing at unknown hosts
- CLAUDE.md with "system:" or "ignore previous" patterns
- Settings with `enableAllProjectMcpServers: true`

## Secret rotation runbook

Triggered when secret scanner blocks a pasted token, OR when audit reveals a token in transcript:

1. **Identify token** — service, scope, account
2. **Rotate immediately** — revoke at provider console
3. **Issue new credential** with minimum scope needed
4. **Inject via env var or secret manager**, never paste
5. **Search transcripts**: `grep -r 'PATTERN' ~/.claude/projects/*/` 
6. **Wipe matched transcripts** — `.jsonl` lines
7. **Verify rotation** with a test call
8. **Document in ADR** — what was leaked, how, what changed

## Audit logging

PostToolUse hook stream to log:

```bash
# .claude/scripts/log-tool-use.sh
#!/usr/bin/env bash
input="$(cat)"
ts=$(date -Iseconds)
tool=$(jq -r '.tool_name // "?"' <<< "$input")
mkdir -p "${CLAUDE_PROJECT_DIR}/.claude/logs"
echo "$ts $tool" >> "${CLAUDE_PROJECT_DIR}/.claude/logs/audit.log"
```

`.claude/logs/` in `.gitignore`. Rotate weekly:

```bash
# cron: weekly
find .claude/logs -name '*.log' -mtime +7 -exec gzip {} \;
find .claude/logs -name '*.log.gz' -mtime +30 -delete
```

## When deny rules aren't enough

Deny rules apply only to Claude's built-in Read/Edit. A `bash cat ~/.ssh/id_rsa` bypasses them. Three counter-measures:

1. `guard-bash.sh` blocks the bash invocation
2. `/sandbox` enforces at OS level (filesystem restricted)
3. Audit log captures the attempt regardless

Each individually has bypass paths. Combined → 6-layer defense.

## EU AI Act compliance (effective Aug 2, 2026)

If shipping to EU, mandatory:

- **Adversarial testing** in quality management
- **Risk management** documentation
- **Conformity assessment** before high-risk AI deployment

Tools: PyRIT (Microsoft) for red-teaming, Guardrails AI for output validation, NIST AI RMF TEVV framework.

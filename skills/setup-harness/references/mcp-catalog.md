# MCP Server Catalog (March 2026)

## MCP tax — read first

Every MCP server consumes context window via tool definitions and protocol overhead. Playwright MCP alone: 26+ tool definitions, 3,000+ accessibility nodes per snapshot, ~114K tokens per typical browser task. Playwright **CLI** for the same job: ~27K. agent-browser: ~5.5K.

**Rule of thumb**: prefer CLI tools when the agent only needs to *call* the service. Reserve MCP for tasks needing protocol features (bidirectional resources, structured tool definitions, vendor-specific schemas).

---

## Detection → MCP mapping (project type)

| Detection | Recommendation | Reason |
|-----------|---------------|--------|
| `@supabase/supabase-js` / `supabase-py` in deps | `supabase` MCP **or** `supabase` CLI | CLI fine for migrations/SQL; MCP for resource browsing |
| `sentry-sdk` in deps | `sentry` MCP | Cross-issue analytics genuinely benefits from MCP |
| GitHub repo | `gh` CLI **first**, MCP only if multi-repo orchestration | `gh` already covers 95% |
| `pg` / `psycopg` / `sqlalchemy` | `postgres` MCP **or** `psql` CLI | CLI for one-off queries |
| Browser app | **Playwright CLI** (NOT MCP) | 4x token-efficient; agent-browser 5.7x for ref-based |
| iOS app | XcodeBuildMCP | 59 tools, Sentry-acquired (March 2026) |
| Android-only | mobile-mcp **or** Appium MCP | accessibility-tree-based |
| iOS+Android cross-platform | mobile-mcp | platform-independent |
| React Native | Detox (test gen) + mobile-mcp (exploratory) | Wix gray-box |
| API project | Hurl CLI (NOT MCP) | plain-text HTTP tests, libcurl-based |
| gRPC | grpcurl CLI + Pact contracts | CLI is enough |
| Bash/CLI app | bats-core (test framework, not MCP) | TAP output |
| Stripe in deps | `stripe` MCP | Resource exploration genuinely useful |
| Slack-sdk | `slack` MCP | Channel/message resources |
| Terraform | `terraform test` + Conftest+OPA (NOT MCP) | Native tooling sufficient |
| Kubernetes | kubeconform + Conftest (NOT MCP) | Schema validation deterministic |
| Popular libs (React, FastAPI, etc.) | `context7` MCP (if not plugin-provided) | Library docs lookup |

---

## E2E testing tools — the most consequential decision

Anthropic's harness-design research drove dramatic perf gains by adding browser automation. But choice of tool changes cost 4x:

| Tool | Type | Token cost | Best for |
|------|------|-----------|---------|
| Playwright MCP | MCP | ~114K/task | **Test suite generation** (Planner/Generator/Healer subagents v1.56+) |
| Playwright CLI (`@playwright/cli`) | CLI | ~27K/task | **Self-test loop** in long sessions |
| agent-browser (Vercel Labs) | CLI | ~5.5K/task | **Exploratory** — ref pattern beats CSS selectors |

Workflow: use Playwright MCP **once** to generate a stable test suite, then run those tests via Playwright CLI in subsequent sessions. The MCP's 3-agent setup (Planner builds exploration plan, Generator writes test code, Healer auto-fixes selectors after UI changes) is genuinely better than hand-writing the suite.

---

## Mobile

| Tool | Target | Notes |
|------|--------|-------|
| XcodeBuildMCP | iOS / Xcode 26.3 | Sentry-acquired. 59 tools. Build errors as structured JSON |
| iOS Simulator MCP | iOS Simulator | Use v1.3.3+ (earlier had command-injection CVE) |
| mobile-mcp | iOS+Android | Native accessibility tree, platform-independent |
| Appium MCP | iOS+Android (existing Appium infra) | Up to 90% maintenance cost reduction vs. raw Appium |
| Detox | React Native | Wix gray-box, monitors async ops to prevent flakes |
| Maestro MCP | Mobile general | YAML, prototype/smoke |

---

## Desktop

| Platform | Accessibility API | MCP tool |
|----------|------------------|---------|
| macOS | NSAccessibility / AXUIElement | macos-ui-automation-mcp, mcp-server-macos-use |
| Windows | UIAutomation | Terminator (1.3k stars, "Playwright for Windows", Rust) |
| Linux | AT-SPI2 | kwin-mcp (KDE Plasma 6) |
| Electron | Chromium accessibility | circuit-mcp, Playwright MCP forks |
| Tauri (Win/Linux) | tauri-driver (official) | WebDriver-based |
| Tauri (macOS) | tauri-webdriver (community) | macOS WebDriver, very new (Feb 2026) |

Native desktop without selectors: TestDriver.ai (Computer-Use SDK, screenshot-based, $$).

---

## API / Backend

| Tool | Use | Why agent-friendly |
|------|-----|-------------------|
| Hurl | HTTP E2E (plain text, libcurl) | Plain-text format, deterministic CI run |
| Pact | Microservice contract tests | Generate consumer tests → verify provider in CI |
| grpcurl | gRPC smoke | CLI-based |
| Testcontainers | DB integration | migrate → seed → test → destroy |

---

## AI/ML stack (6-layer testing)

| Layer | Tools |
|-------|-------|
| Data quality | GX Core, Soda Core, Elementary, dbt tests / dbt-expectations |
| Model benchmarks | lm-evaluation-harness (EleutherAI), LightEval (HF), HELM, Inspect AI |
| LLM application quality | DeepEval (pytest), promptfoo (YAML+CI), RAGAS |
| Agent eval | Maxim AI, LangSmith, Arize Phoenix, Langfuse |
| Safety/guardrails | PyRIT (Microsoft), Guardrails AI, NeMo Guardrails (NVIDIA), Constitutional Classifiers |
| Observability / drift | Arize, WhyLabs, Evidently AI, Langfuse |

---

## .mcp.json template

```json
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": ["-y", "@supabase/mcp-server-supabase"],
      "env": {
        "SUPABASE_ACCESS_TOKEN": ""
      }
    },
    "sentry": {
      "command": "npx",
      "args": ["-y", "@sentry/mcp-server"],
      "env": {
        "SENTRY_AUTH_TOKEN": ""
      }
    }
  }
}
```

**Security**: in your user-global `~/.claude/settings.json` set:

```json
{ "enableAllProjectMcpServers": false }
```

This prevents cloned repos from auto-loading hostile MCP servers. Each project's `.mcp.json` is then opt-in.

---

## Pre-check before recommending

1. Plugin not already providing the same MCP (e.g., context7 may ship via plugin marketplace)
2. Dependency actually exists in `requirements.txt` / `package.json` / `go.mod`
3. User has the required auth tokens / API keys
4. **CLI alternative exists and is sufficient** — default to CLI
5. MCP package name is current (Anthropic's MCP namespace shifted in 2025–2026; verify with `npm view`)

---

## Verifying package names

MCP ecosystem churns. Before adding to `.mcp.json`, verify:

```bash
npm view @supabase/mcp-server-supabase version 2>/dev/null || echo "package name may have changed"
npm view @sentry/mcp-server version 2>/dev/null
```

If a package 404s, the canonical source is the vendor's docs page, not Claude's memory.

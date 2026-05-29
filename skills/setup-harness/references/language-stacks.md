# Per-language harness stacks (March 2026)

Picks favor: fast PostToolUse-fit, strong custom-rule support, auto-fix coverage.

---

## TypeScript / JavaScript

| Layer | Tool | Why |
|-------|------|-----|
| PostToolUse (ms) | Biome format → Oxlint | Rust, 50–100x faster than ESLint+Prettier |
| Pre-commit (s) | Lefthook → Oxlint + `tsc --noEmit` | Full-file lint + type check |
| CI (min) | ESLint (custom architectural rules) + vitest/jest | Deep analysis |
| Custom rules | eslint-plugin-local-rules **or** ast-grep | Architecture boundaries |
| E2E | Playwright CLI (NOT MCP) or agent-browser | 4–20x token efficient |
| Frameworks | Next.js, Vite, Astro, Nuxt — same stack |

Production users: Shopify, Airbnb, Mercedes-Benz, Linear, Framer (Oxlint).

---

## Python

| Layer | Tool | Why |
|-------|------|-----|
| PostToolUse (ms) | Ruff `--fix` + Ruff `format` | Single Rust binary, Flake8+isort+pyupgrade+pydocstyle+Black combined |
| Pre-commit (s) | Lefthook → Ruff + mypy | Type check |
| CI (min) | Ruff + mypy + pytest | Full |
| Custom rules | ast-grep or pylint custom checkers | Architecture (Ruff has no custom rules) |
| Security | Ruff `S` rules + bandit (CI) | OWASP-style |
| Web frameworks | FastAPI, Django, Flask, Litestar — same stack |
| Data | dbt + dbt-expectations / GX for pipelines |

---

## Go

| Layer | Tool |
|-------|------|
| PostToolUse | gofumpt + golangci-lint (fast subset) |
| Pre-commit | golangci-lint `--fix` |
| CI | golangci-lint (full) + `go test ./...` |
| Required linters | staticcheck, gosec, errcheck, revive, govet, gofumpt, gci, modernize |

Used by: Kubernetes, Prometheus, Terraform.

---

## Rust

| Layer | Tool |
|-------|------|
| PostToolUse | rustfmt |
| Pre-commit | cargo clippy pedantic |
| CI | cargo clippy + cargo test + cargo audit |

Required `Cargo.toml`:
```toml
[lints.clippy]
pedantic = { level = "warn", priority = -1 }
unwrap_used = "deny"
expect_used = "deny"
allow_attributes = "deny"
dbg_macro = "deny"
```

`allow_attributes = "deny"` is critical — prevents agent silencing lints via `#[allow(...)]`.

---

## Swift

| Layer | Tool |
|-------|------|
| PostToolUse | swift-format + SwiftLint --autocorrect |
| Pre-commit | SwiftLint + swiftc -typecheck |
| CI | SwiftLint + XCTest |
| Custom rules | SwiftLint regex/AST-based custom rules |
| iOS E2E | XcodeBuildMCP (Sentry, 59 tools) — Xcode 26.3+ native MCP support |

---

## Kotlin

| Layer | Tool |
|-------|------|
| PostToolUse | ktfmt (40% faster than ktlint) |
| Pre-commit | detekt |
| CI | detekt + JUnit |
| Custom rules | detekt custom rules |
| Android E2E | mobile-mcp or Appium MCP |

---

## Ruby

| Layer | Tool |
|-------|------|
| PostToolUse | RuboCop -a |
| Pre-commit | RuboCop + Sorbet (`srb tc`) |
| CI | RuboCop + RSpec + brakeman (security) |
| Custom rules | RuboCop custom cops |

---

## .NET / C#

| Layer | Tool |
|-------|------|
| PostToolUse | dotnet format |
| Pre-commit | dotnet build /warnaserror + Roslyn analyzers |
| CI | dotnet test + sonarscanner |
| Security | Microsoft.CodeAnalysis.NetAnalyzers |

---

## Elixir

| Layer | Tool |
|-------|------|
| PostToolUse | mix format |
| Pre-commit | credo --strict + dialyxir |
| CI | credo + ExUnit + sobelow (security) |

---

## PHP

| Layer | Tool |
|-------|------|
| PostToolUse | PHP-CS-Fixer |
| Pre-commit | PHPStan level max + psalm |
| CI | PHPStan + PHPUnit + Rector (refactoring) |

---

## Java

| Layer | Tool |
|-------|------|
| PostToolUse | google-java-format (or palantir-java-format) |
| Pre-commit | Spotless + Error Prone |
| CI | Checkstyle + SpotBugs + JUnit + OWASP dep-check |

---

## SQL / database migrations

| Layer | Tool |
|-------|------|
| Schema lint | sqlfluff |
| Migration safety | Squawk (Postgres) — block dangerous DDL |
| Schema drift | atlas / dbmate / sqitch verify |
| Data tests | dbt + dbt-expectations / Great Expectations |

---

## Infra (Terraform / K8s / Docker)

| Tool | Use |
|------|-----|
| `terraform test` (v1.6+) | Native HCL tests |
| Conftest + OPA | Policy checks on `terraform plan` output |
| Terratest | Real-infra integration tests in sandbox |
| kubeconform | K8s manifest schema validation |
| container-structure-test | Docker image structure |

Required PreToolUse blocks:
- `terraform apply` against prod
- `kubectl apply` against prod context
- `docker push` without scan

---

## Selection matrix

| Criterion | Pick |
|-----------|------|
| Fastest PostToolUse runner | Rust-based (Oxlint, Ruff, gofumpt, rustfmt) |
| Strongest custom-rule support | ESLint + ast-grep (TS/multi), detekt (Kotlin), SwiftLint (Swift) |
| Best agent-error messages | tools supporting structured stdout — Ruff, Oxlint, golangci-lint |
| Best E2E for agents | Playwright CLI or agent-browser (NOT MCP for self-test loops) |

---

## Decision rule

For a new project: pick the **fastest Rust-based linter + formatter combo** for the chosen language. Speed lets PostToolUse run on every edit without lag, which closes the feedback loop in milliseconds. Defer slower, deeper checks to pre-commit and CI.

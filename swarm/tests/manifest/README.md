# Manifest Validation Tests

Validates `.claude-plugin/plugin.json` against the plugin manifest schema.

## What is covered

| Case | File | Expects |
|------|------|---------|
| Real manifest | `.claude-plugin/plugin.json` | exit 0, stdout `OK:` |
| Missing `name` | temp fixture | exit 1 |
| Missing `version` | temp fixture | exit 1 |
| Bad `version` format (`abc`) | temp fixture | exit 1 |
| `keywords` not an array | temp fixture | exit 1 |

Fixtures are generated in a `mktemp -d` temp dir and cleaned up on exit.

## How to run

```bash
bash tests/manifest/test-validate.sh
```

All cases must pass for exit 0. Output per case: `PASS: <label>` or `FAIL: <label>`.
Final line: `PASSED N/N`.

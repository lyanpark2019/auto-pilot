---
topic: auto-pilot-configuration
owner: scripts/_config.py
---

# auto-pilot configuration

Runtime defaults are centralized in `scripts/_config.py` and loaded through
`_config.load()`. Bounds are enforced in `AutoPilotConfig.__post_init__`; invalid
values fail fast before the headless loop or dispatch gate starts.

| Setting | Env var | Default | Bounds | Consumer |
|---|---|---:|---|---|
| Claude binary | `CLAUDE_BIN` | `shutil.which("claude")` or `claude` | non-empty path/name | `scripts/headless-loop.py` |
| Preflight TTL | `AUTO_PILOT_PREFLIGHT_TTL_SEC` | `900` | `60..86400` seconds | `scripts/_dispatch.py`, `scripts/_config.py` |
| Max loop iterations | `default_max_iter` dataclass field | `100` | `1..10000` | `scripts/headless-loop.py --max-iter` |
| Sleep between iterations | `default_sleep_sec` dataclass field | `10` | `1..3600` seconds | `scripts/headless-loop.py --sleep` |
| Per-session timeout | `default_timeout_build_sec` dataclass field | `14400` | `>0..86400` seconds | `scripts/headless-loop.py --timeout-build` |
| Max spend | `default_max_cost_usd` dataclass field | `50.0` | `>0..10000` USD | `_budget.check_caps` |
| Max tokens | `default_max_tokens` dataclass field | `50000000` | `1..1000000000` | `_budget.check_caps` |
| Fallback per-iteration cost | `default_per_iter_cost_estimate_usd` dataclass field | `0.50` | `>0..1000` USD | `_budget.parse_session_usage` fallback |
| Max concurrent Claude processes | `default_max_concurrent_claude` dataclass field | `4` | `1..64` | `_budget.count_claude_pids` cap |

## Profiles

The plugin currently ships one production-safe default profile. Local overrides
are made through CLI flags for per-run budget/time controls or the two env vars
above for host integration. There is no dev/staging/prod split because the
plugin runs against the caller's checkout rather than a deployed service.

## Verification

- `tests/test_config.py` checks default values, env overrides, and every numeric
  lower/upper bound.
- `tests/test_mypy_scope.py` keeps `scripts/_config.py` in the strict mypy set.
- `docs/configuration.md` is guarded by `tests/test_config.py` so env var docs do
  not drift from `_config.load()`.

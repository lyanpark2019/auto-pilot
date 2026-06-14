# auto-pilot tests

Pytest suite covering the orchestrator helper, the contract/dispatch/worktree/discovery/evidence helper layer, the eval harness, and the wired hook scripts (26 hooks in hooks/hooks.json).

## Run

```bash
pytest tests/ -v
```

## Layout

- `conftest.py` — `in_tmp_cwd`, `hooks_dir`, `sample_spec`, `clean_env` fixtures + `scripts/` on `sys.path`
- `test_orchestrator.py` — direct calls into `orchestrator.main()` for the core subcommands it covers (init / phase-start / phase-end / pivot-check trip / status / stop / resume / discover / review-status) plus error paths. Note: `orchestrator.py` registers more subcommands than the test exercises (e.g. dispatch-contract-check, round-budget, ledger-append/rebalance, plus promotion/recover) — see `_build_cli_parser` in `scripts/orchestrator.py`.
- `test_hooks_*.py` (10 files) — `subprocess`-runs each hook with JSON on stdin, asserts exit code + stderr, grouped by concern: auth / composition / gates / guards / ledger / notebooklm / pm_final_report / session / shellcheck_on_write / wiring. (Additional script-style hook self-tests live under `hooks/test_*.py`.)

## Notes

- Tests are hermetic: each writes state into pytest's `tmp_path`, never touches the repo's `.planning/`
- The `clean_env` fixture wipes `AUTO_PILOT_FORCE_COMPOSITION_ROOT` / `AUTO_PILOT_BASH_BYPASS` so bypass-aware tests are deterministic
- `preflight-path.sh` warns on `/var/folders`, so the silence test uses `~/.cache/auto-pilot-tests/` instead of `tmp_path`

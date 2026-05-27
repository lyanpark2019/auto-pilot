# auto-pilot tests

Pytest suite covering the orchestrator helper and all four hook scripts.

## Run

```bash
pytest tests/ -v
```

## Layout

- `conftest.py` — `in_tmp_cwd`, `hooks_dir`, `sample_spec`, `clean_env` fixtures + `scripts/` on `sys.path`
- `test_orchestrator.py` — direct calls into `orchestrator.main()` for every subcommand (init / phase-start / phase-end / pivot-check trip / status / stop) plus error paths
- `test_hooks.py` — `subprocess` runs each hook with JSON on stdin, asserts exit code + stderr

## Notes

- Tests are hermetic: each writes state into pytest's `tmp_path`, never touches the repo's `.planning/`
- The `clean_env` fixture wipes `AUTO_PILOT_FORCE_COMPOSITION_ROOT` / `AUTO_PILOT_BASH_BYPASS` so bypass-aware tests are deterministic
- `preflight-path.sh` warns on `/var/folders`, so the silence test uses `~/.cache/auto-pilot-tests/` instead of `tmp_path`

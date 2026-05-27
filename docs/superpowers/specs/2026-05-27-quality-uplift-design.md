# auto-pilot — quality uplift to FAANG tier (v0.3)

**Date:** 2026-05-27
**Status:** Approved (brainstorming → execution)
**Author:** lyanpark2019 (Opus 4.7 PM)
**Scope:** Lift `weighted_score` 79.8 → ≥90 over 12 non-CI dims; resolve 3 open P3 product bugs. CI/CD dim deliberately excluded.

## 1. Goal

Quality-eval baseline (2026-05-27, iteration 0): **79.8 / 100**, Mid-size tier. CI/CD dim scored 50 — frozen and excluded from this uplift.

**Done condition:** Re-score after execution satisfies

```
weighted_non_ci = (Σ(score_dim × weight_dim) − 50 × 0.03) / 0.97 ≥ 90
```

where weights and scores come from `quality-eval` rubric, CI/CD dim treated as constant 50.

Also resolve 3 P3 product bugs from `orchestrator-bugs-fixed.md` memory:
- `phase-start --phase N` accepts out-of-range / duplicate phases
- Round counter hardcoded `"round": 1`, never bumps
- `plugin.json` version `0.1.0` ↔ git tag drift

## 2. Architecture

Single PM session (Opus 4.7, this Claude Code session) dispatches Claude general-purpose subagents in parallel waves via the `Agent` tool. PM does verification (read diff + `ruff`/`mypy`/`shellcheck`/`pytest`) and commits between waves. No middleware runtime; native to Claude Code.

```
[PM: Opus 4.7]
   │
   │  Wave A — 6 subagents dispatched in ONE message (parallel)
   │  ┌─────┬─────┬─────┬─────┬─────┬─────┐
   ├──┤ C1  │ C2  │ C3  │ C4  │ C5  │ C6  │
   │  └─────┴─────┴─────┴─────┴─────┴─────┘
   │  PM: read each diff → run gates → commit (×6)
   │
   │  Wave B — 2 subagents in ONE message (parallel)
   │  ┌──────┬──────┐
   ├──┤ C7a  │ C12  │
   │  └──────┴──────┘
   │  PM: gates → commit (×2)
   │
   │  Wave C — 1 subagent (sequential dependency on C7a)
   │  ┌──────────┐
   ├──┤ C7b+C11  │
   │  └──────────┘
   │  PM: gates → commit (×1)
   │
   └── Final: invoke /quality-eval skill → assert weighted_non_ci ≥ 90
```

Each subagent receives a self-contained brief (no "based on prior context"): target dim, current score, target score, exact file paths, target line ranges, acceptance gates (commands to run), and an explicit don't-touch list.

## 3. Contracts

### Wave A (6 parallel, fully isolated file ownership)

#### C1 — Structured logging (logging 68 → 90)
- **Owns:** `scripts/orchestrator.py`, `scripts/headless-loop.py`, new `scripts/_log.py`
- **Action:** Add `scripts/_log.py` exposing `event(name: str, **kv)` helper that emits `event=<name> k1=v1 k2=v2` to stderr. Replace every `print(..., file=sys.stderr)`, `sys.stderr.write(...)`, and `print(json.dumps(...))` in both Python scripts with `event(...)` calls preserving information.
- **Must not:** touch env var reads, hooks, tests, or markdown.
- **Gates:** `pytest tests/ -q` passes (tests assert on stderr content — workers may need to update assertion strings, but only in `tests/test_orchestrator.py` substring checks already covering the same key info).

#### C2 — LLM prompt externalization (llm_prompt_quality 65 → 90)
- **Owns:** new `prompts/headless.md`, new `scripts/_prompts.py`, new `tests/test_prompts.py`
- **Action:** Copy `HEADLESS_PROMPT_PREAMBLE` (currently in `scripts/headless-loop.py:50-63`) into `prompts/headless.md` verbatim. Also extract the per-iteration prompt template at `scripts/headless-loop.py:155-162` into `prompts/iteration.md` with `{iter_n}` `{phase}` placeholders. Create `scripts/_prompts.py` with `load(name: str) -> str` and `render(name: str, **vars) -> str` (uses `str.format_map`). Write fixture test in `tests/test_prompts.py` verifying load + render for both prompts, asserting placeholder resolution.
- **Read-only ref:** `scripts/headless-loop.py` (do not modify; C7b wires the import).
- **Gates:** `pytest tests/test_prompts.py -v` passes.

#### C3 — Centralized config (configuration 75 → 90)
- **Owns:** new `scripts/_config.py`
- **Action:** Create dataclass `AutoPilotConfig` consolidating: `CLAUDE_BIN`, `HEADLESS_ENV` dict, `DEFAULT_TIMEOUT_BUILD` (4×3600), `DEFAULT_SLEEP_SEC` (10), `DEFAULT_MAX_ITER` (100), `MONITORED_PORTS` (8000/3000/5000/8080). Expose `load() -> AutoPilotConfig` reading env with documented defaults. No external dependencies (stdlib `dataclasses` + `os` only).
- **Read-only ref:** `scripts/headless-loop.py` (do not modify).
- **Gates:** `python3 -c "from scripts._config import load; print(load())"` succeeds.

#### C4 — Hooks fail-loud on JSON parse (error_handling 78 → 90)
- **Owns:** `hooks/pre-edit-composition-root.sh`, `hooks/pre-bash-guard.sh`, `hooks/post-deploy-verify.sh`
- **Action:** Replace the inline `python3 -c '...' 2>/dev/null` pattern in each hook with one that catches `json.JSONDecodeError` explicitly and emits `auto-pilot: WARNING malformed tool_input json` to stderr, then exits 0 (still non-blocking). Keep current behavior on valid input.
- **Must not:** touch `hooks/preflight-path.sh` (no JSON read), `hooks/hooks.json`, or any other file.
- **Gates:** `pytest tests/test_hooks.py -q` passes (existing tests cover happy + empty path; add one test per hook for malformed JSON warning).

#### C5 — Perf baseline (perf_budget 70 → 85)
- **Owns:** new `tests/test_perf.py`, new `docs/perf-budget.md`
- **Action:** Add `pytest-benchmark` test exercising `orchestrator.cmd_status`, `cmd_phase_start`, `cmd_phase_end`. Assert each completes in `<50ms` (budget). Document budgets + measurement methodology in `docs/perf-budget.md`. `pytest-benchmark` is already installed (verified 5.2.3).
- **Gates:** `pytest tests/test_perf.py --benchmark-only -q` passes within budget.

#### C6 — headless-loop coverage (test_quality 85 → 92)
- **Owns:** new `tests/test_headless_loop.py`
- **Action:** Add tests that mock `subprocess.Popen` (via `unittest.mock.patch`) and `git rev-parse` / `git reset --hard` to exercise `loop_iteration`: success path advances state, timeout path (`rc=124`) triggers rollback, failed status path triggers rollback, terminal state (`success`/`stopped`/`pivot-needed`/`failed`) short-circuits before subprocess spawn. Minimum 5 tests.
- **Read-only ref:** `scripts/headless-loop.py` (do not modify).
- **Gates:** `pytest tests/test_headless_loop.py -v` passes.

### Wave B (2 parallel, after PM commits all Wave A)

#### C7a — Strict types + docstrings + narrow exception (type_safety 82→92, documentation 82→90, error_handling polish)
- **Owns:** `scripts/orchestrator.py`, `scripts/headless-loop.py`, new `mypy.ini`
- **Action:**
  - Introduce `TypedDict`: `PhaseEntry`, `State` in `scripts/orchestrator.py` and use them throughout. Update return types accordingly.
  - Add docstrings (Args/Returns/Raises sections) to every `cmd_*` function in `orchestrator.py`, plus `_count_phases`, `main`. In `headless-loop.py`, add docstrings to `run_claude_session`, `loop_iteration`, `main`.
  - In `headless-loop.py:118` replace `except Exception:` with `except (OSError, subprocess.SubprocessError):` (the realistic failure modes for `terminate`/`wait`/`kill`).
  - Add `mypy.ini` with `strict = True`, `files = scripts`. Make `mypy scripts/` pass with strict mode (no `# type: ignore` unless justified inline).
- **Must not:** extract any module (C7b does that); touch hooks, tests, prompts, config.
- **Gates:** `mypy scripts/` clean, `pytest tests/ -q` passes.

#### C12 — plugin.json bump + ruff cleanup (cosmetic)
- **Owns:** `.claude-plugin/plugin.json`, `tests/conftest.py`, `tests/test_orchestrator.py`
- **Action:**
  - Bump `version` field in `plugin.json` from `0.1.0` to `0.3.0`.
  - Run `python3 -m ruff check --fix scripts/ tests/` (removes 2 unused imports: `os` in `conftest.py:3`, `pytest` in `test_orchestrator.py:6`).
- **Gates:** `python3 -m ruff check scripts/ tests/` returns clean.

### Wave C (1 sequential, after PM commits Wave B)

#### C7b + C11 merged — extract `_state.py`, wire imports, P3 phase-start validation + round bump (architecture 85→92, P3 bugs)
- **Owns:** `scripts/orchestrator.py`, `scripts/headless-loop.py`, new `scripts/_state.py`, `tests/test_orchestrator.py`
- **Action:**
  - Extract `STATE_DIR`, `STATE_FILE`, `load_state`, `save_state`, `utc_now` from `orchestrator.py` into new `scripts/_state.py`. Both `orchestrator.py` and `headless-loop.py` import from it (removes the duplicate `load_state` + `STATE_FILE` in `headless-loop.py:42-73`).
  - Wire `scripts/_config.py` (from C3) into `headless-loop.py`: replace hardcoded constants with `load()` values.
  - Wire `scripts/_prompts.py` (from C2) into `headless-loop.py`: replace inline `HEADLESS_PROMPT_PREAMBLE` string with `prompts.render("headless")`; replace iteration prompt construction with `prompts.render("iteration", iter_n=n, phase=phase)`.
  - **P3 phase-start validation:** in `cmd_phase_start`, reject if `args.phase < 1` or `args.phase > state["total_phases"]` (exit 2 with explicit message); if same phase already in `state["phases"]` with `status == "running"`, reject (exit 2); if same phase appears with terminal status (`success`/`failed`/`pivot-needed`), treat as retry — bump that entry's `round` by 1 and reset `status` to `running` instead of appending.
  - Add 4 new tests in `tests/test_orchestrator.py`: out-of-range phase rejected, duplicate running phase rejected, retry-bumps-round, retry-resets-status.
- **Must not:** touch hooks, prompts/, config defaults.
- **Gates:** `mypy scripts/` clean (TypedDicts from C7a still valid), `pytest tests/ -q` passes (≥4 new tests).

## 4. File-ownership matrix (parallel safety)

| File | C1 | C2 | C3 | C4 | C5 | C6 | C7a | C12 | C7b+C11 |
|---|---|---|---|---|---|---|---|---|---|
| `scripts/orchestrator.py` | W | — | — | — | — | — | W | — | W |
| `scripts/headless-loop.py` | W | R | R | — | — | R | W | — | W |
| `scripts/_log.py` (new) | W | — | — | — | — | — | — | — | — |
| `scripts/_prompts.py` (new) | — | W | — | — | — | — | — | — | — |
| `scripts/_config.py` (new) | — | — | W | — | — | — | — | — | — |
| `scripts/_state.py` (new) | — | — | — | — | — | — | — | — | W |
| `prompts/headless.md` (new) | — | W | — | — | — | — | — | — | — |
| `prompts/iteration.md` (new) | — | W | — | — | — | — | — | — | — |
| `hooks/pre-*.sh`, `post-*.sh` | — | — | — | W | — | — | — | — | — |
| `tests/test_prompts.py` (new) | — | W | — | — | — | — | — | — | — |
| `tests/test_perf.py` (new) | — | — | — | — | W | — | — | — | — |
| `tests/test_headless_loop.py` (new) | — | — | — | — | — | W | — | — | — |
| `tests/test_hooks.py` | — | — | — | W | — | — | — | — | — |
| `tests/test_orchestrator.py` | (R)* | — | — | — | — | — | — | W | W |
| `tests/conftest.py` | — | — | — | — | — | — | — | W | — |
| `mypy.ini` (new) | — | — | — | — | — | — | W | — | — |
| `.claude-plugin/plugin.json` | — | — | — | — | — | — | — | W | — |
| `docs/perf-budget.md` (new) | — | — | — | — | W | — | — | — | — |

`W` = write/edit, `R` = read-only reference. `(R)*` for C1 = may need to update stderr substring matchers in existing orchestrator tests (those are owned by W7a/W12/W7b+C11 in later waves, so C1 must complete its edits and tests first — Wave A ordering).

Within each wave, no two `W` cells share a row. ✓

## 5. Acceptance + verification

**Per-contract (PM-driven, after subagent returns):**
1. Read full diff.
2. Run gates: `python3 -m ruff check scripts/ tests/`, `python3 -m mypy scripts/`, `shellcheck hooks/*.sh`, `python3 -m pytest tests/ -q`.
3. If any gate fails: PM fixes inline (≤10 lines) OR re-dispatches the subagent with the failure log; do not commit failing code.
4. Commit with `Co-Authored-By: Claude Opus 4.7` trailer + contract id (`C1` … `C12`) in subject.

**Final (after Wave C committed):**
- Re-invoke `quality-eval` skill.
- Compute `weighted_non_ci = (raw_weighted_score − 50 × 0.03) / 0.97`.
- Gate: `weighted_non_ci ≥ 90`.
- If gate fails: identify worst dim, open a single follow-up contract, repeat. Max 1 follow-up round (then surface to user).

## 6. Risks + mitigations

| Risk | Mitigation |
|---|---|
| Wave A subagent edits same file as another (race) | File-ownership matrix in §4 — every parallel pair has disjoint `W` columns. |
| C7a strict-mode surfaces hidden `Any` exceeding the budget | If `mypy --strict` reveals ≥20 violations, PM splits into C7a₁ (`orchestrator.py`) and C7a₂ (`headless-loop.py`) sequential. |
| C1 changes stderr text so existing tests break | C1 brief explicitly allows updating substring matchers in `tests/test_orchestrator.py` for stderr changes only (no logic changes). All stderr assertions checked first by PM before dispatch. |
| Subagent invents new dependencies (e.g., `structlog`, `pydantic`) | Each brief explicitly says "stdlib only" + "no new pip installs". |
| Re-score still < 90 after Wave C | Follow-up contract from §5; capped at 1 round. |

## 7. Out of scope

- CI/CD pipeline (GitHub Actions workflow, pre-commit, branch protection) — deliberately excluded per user instruction.
- Headless-loop integration tests (real `claude -p` subprocess) — Wave C only adds mock-subprocess tests.
- Performance regression tracking in CI — perf budget doc only (C5).
- Markdown agent contract restructuring (`agents/*.md`) — unchanged.
- Plugin distribution / marketplace publish — deferred.

## 8. Expected projected score (best-case)

| Dim | Before | After (target) | Δ × weight |
|---|---|---|---|
| logging | 68 | 90 | +1.98 |
| llm_prompt_quality | 65 | 90 | +1.25 |
| configuration | 75 | 90 | +1.05 |
| error_handling | 78 | 90 | +1.20 |
| perf_budget | 70 | 85 | +0.90 |
| test_quality | 85 | 92 | +0.91 |
| type_safety | 82 | 92 | +0.90 |
| documentation | 82 | 90 | +0.56 |
| architecture | 85 | 92 | +0.35 |
| code_structure | 90 | 90 | 0 |
| async_correctness | 90 | 90 | 0 |
| security | 88 | 88 | 0 |
| **ci_cd (frozen)** | **50** | **50** | **0** |
| **Total** | **79.80** | **~88.90** | **+9.10** |

Renormalized: `(88.90 − 50×0.03) / 0.97 = 87.40 / 0.97 ≈ 90.10` → passes gate.

Margin is thin. If any dim underperforms target by ≥3 pts, the follow-up round trips. Acceptable.

## 9. Memory updates

After Wave C completes + gate passes:
- Update `~/.claude/projects/-Users-lyan-Documents-Project-auto-pilot/memory/orchestrator-bugs-fixed.md` to mark P3 items resolved.
- Add new memory `~/.claude/projects/.../memory/quality-uplift-v03.md` with final scores, files added, contract trail.
- Refresh `MEMORY.md` index.

## 10. Execution sequence (PM checklist)

1. Commit this spec.
2. Wave A: single message with 6 `Agent` calls (subagent_type=general-purpose). Each gets its contract section verbatim + the file-ownership matrix + acceptance gates.
3. PM: for each returned diff, read → gates → fix-or-redispatch → commit.
4. Wave B: single message with 2 `Agent` calls. Verify + commit.
5. Wave C: 1 `Agent` call. Verify + commit.
6. Final: `/quality-eval` skill, assert ≥90 renormalized.
7. Save memory updates.
8. Push to `origin/main` (lyanpark2019).

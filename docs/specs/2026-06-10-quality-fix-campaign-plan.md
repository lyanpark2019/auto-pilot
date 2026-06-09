# Plugin Quality-Fix Campaign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement task-by-task. Steps use checkbox (`- [ ]`) syntax. TDD is mandatory: write the failing test, watch it fail, minimal green, commit.

**Goal:** Close every P1 (and the meaningful P2s) from the 2026-06-10 six-dimension cold audit so a re-audit finds 0 new P0/P1, leaving only stated architectural-limit residuals.

**Architecture:** Five independent fix clusters (A–E). Each cluster is a worker contract scoped to a small file set, TDD'd, then dual-adversarially reviewed (Codex `--sandbox read-only` + cold Claude). Clusters A–D are code; E is docs. A re-audit phase re-runs the affected-dimension auditors and reports honest new scores. No "100/perfect" verdict is emitted — the terminal honest state is "0 P0/P1 open, 0 new on re-audit, residual = architectural limits."

**Tech Stack:** Python 3.13 (pytest, mypy, ruff), bash 3.2/BSD-compatible hooks (shellcheck 0.11.0), JSON Schema 2020-12, agent/skill markdown.

**Audit baseline (scores to beat):** Architecture 84 · Docs 78 · Tests 76 · Agents 74 · Security 71 · Enforcement 67.

**Ground rules for every cluster**
- Each guard fix is TEST-FIRST: the failing test reproduces the audit finding before the fix.
- Tests touching the home ledger MUST `monkeypatch.setenv("HOME", str(tmp_path / "home"))`.
- Bundled `.sh`: bash shebang (never zsh), `shellcheck -S warning` clean, no `mapfile`, `sed -i ''`, `find|xargs` without `-print0`.
- Verify per cluster: `python3 -m pytest tests/ -q` + `mypy scripts/ hooks/` + `ruff check scripts/ tests/ hooks/` + `shellcheck hooks/*.sh` + `bash scripts/quality/check-module-size.sh`.
- Commit per task with trailers (`Rejected:`/`Constraint:`/`Not-tested:`/`Confidence:`).

---

## Phase order & rationale

1. **Cluster A — Enforcement guards** first: two fixes (branch-lock refspec, gh-auth regex) change guard behavior for ALL future sessions; landing them early de-risks the rest of the campaign (every later push stops false-tripping).
2. **Cluster B — Security/env** next: the reviewer env leak (#5) gates safe dispatch of the dual reviewers used by every later cluster's review step.
3. **Cluster C — Test rigor**, **D — Agents**, **E — Docs** are mutually independent → can run in parallel after A+B land.
4. **Re-audit** last.

---

## Cluster A — Enforcement guards

**Files:**
- Modify: `hooks/branch-lock.sh`
- Modify: `hooks/gh-auth-preflight.sh`
- Modify: `hooks/pre-reviewer-write.sh`
- Test: `tests/test_hooks_guards.py`, `hooks/test_*` (script-style where applicable)

### Task A1: branch-lock — gate on push REFSPEC, not current branch (audit #1, #2)

Current bug (`hooks/branch-lock.sh:80-96`): for a `push` segment it checks `git branch --show-current` and denies on main/master regardless of the push target. Pushing a feature branch while HEAD=main (normal post-merge state) is wrongly blocked → trains reflexive `AUTO_PILOT_MAIN_OK=1`, defeating the guard.

**Target behavior (the test contract):**

| command | HEAD branch | decision |
|---|---|---|
| `git commit -m x` | main | **deny** (commit targets HEAD) |
| `git commit -m x` | feature | allow |
| `git push origin main` | feature | **deny** (dst=main) |
| `git push origin feature` | main | **allow** (dst=feature) |
| `git push origin HEAD:main` | feature | **deny** (dst=main) |
| `git push origin feature:main` | feature | **deny** (dst=main) |
| `git push -u origin feature` | main | **allow** |
| `git push` (bare) | main | **deny** (pushes current=main) |
| `git push origin` (no refspec) | main | **deny** (current=main) |
| `AUTO_PILOT_MAIN_OK=1 git push origin main` | any | allow (bypass) |

**Reference algorithm** (worker implements in bash; commit segments keep the current-branch check, push segments switch to refspec resolution):
```
for each "git <opts> push" segment:
  toks = tokens after `push`, drop any starting with `-` (flags)
  if len(toks) <= 1:                      # bare `git push` or `git push <remote>`
      target_ref = current branch (git -C <dir> branch --show-current)
  else:
      refspec = toks[1]                    # toks[0]=remote, toks[1]=first refspec
      target_ref = part after ':' if ':' in refspec else refspec
  deny if target_ref in {main, master}
for each "git <opts> commit" segment:
  deny if current branch in {main, master}   # unchanged
```

- [ ] **Step 1 — failing tests.** Add to `tests/test_hooks_guards.py` a parametrized test `test_branch_lock_push_refspec` covering every row of the table above (use the existing repo-fixture helpers `_make_feature_repo` / a main-HEAD repo; feed JSON `{"tool_input":{"command":..., "cwd":...}}` to `hooks/branch-lock.sh`; assert `permissionDecision` deny/allow).
- [ ] **Step 2 — watch fail.** `pytest tests/test_hooks_guards.py -k branch_lock_push_refspec -v` → the `push origin feature while HEAD=main` row FAILS (currently denied).
- [ ] **Step 3 — implement** the refspec resolution in `hooks/branch-lock.sh` per the algorithm. Keep the order-independent segment collection (`segs`), the `AUTO_PILOT_MAIN_OK` bypass, the `-C` target resolution.
- [ ] **Step 4 — green + regressions.** `pytest tests/test_hooks_guards.py -v` all pass; `shellcheck hooks/branch-lock.sh` clean.
- [ ] **Step 5 — commit.** `Constraint: push refspec parse is token-based (multi-refspec push honors first dst); documented residual.`

### Task A2: gh-auth-preflight — fire only when `gh` is a command, not a substring (audit #3, #4)

Current bug (`hooks/gh-auth-preflight.sh:42`): regex `(^|[[:space:];|&\`$(])gh[[:space:]]` matches `gh ` anywhere — inside comments/strings/args (`git grep "gh CLI"`, `echo "use gh"`). Denies the whole compound command on those false hits.

**Target:** fire only when, after splitting the command on `;` `&&` `||` `|` newline `(`, some segment's first token (post-leading-whitespace) is exactly `gh`. Second-token `auth` still skips. This kills the substring/comment/arg false-positives while still catching real `gh` invocations anywhere in a chain.

| command | fires? |
|---|---|
| `gh pr list` | yes |
| `gh auth status` | no (auth skip) |
| `git grep "gh CLI"` | **no** (segment starts with `git`) |
| `echo "use gh auth switch"` | **no** (starts with `echo`) |
| `make build && gh release create` | yes (2nd segment starts with `gh`) |
| `# gh active note` | **no** (comment, not a command segment starting with `gh`) |

- [ ] **Step 1 — failing tests.** `tests/test_hooks_guards.py::test_gh_auth_fires_only_on_command` parametrized over the table (feed the command, assert deny-vs-allow given a mismatched cached active user; reuse existing gh-auth test scaffolding — set the cache file to a wrong user so a real fire → deny).
- [ ] **Step 2 — watch fail.** The `git grep "gh CLI"` and `echo "use gh"` rows FAIL (currently fire→deny).
- [ ] **Step 3 — implement.** Replace the substring grep at `:42` with a segment-split + first-token check (a small `python3 -c` is acceptable and more portable than nested bash regex; the hook already shells to python3 for JSON). Keep the `gh auth` / `gh auth switch` cache-purge logic.
- [ ] **Step 4 — green + regressions + `shellcheck hooks/gh-auth-preflight.sh`.**
- [ ] **Step 5 — commit.** `Constraint: segment-split is separator-based; a gh inside an unquoted subshell arg position is treated as a command (intended).`

### Task A3: pre-reviewer-write — fail CLOSED on unparseable payload (audit P2, security-critical)

Current bug (`hooks/pre-reviewer-write.sh:22-29`): for a reviewer role, JSONDecodeError → python `sys.exit(0)` → bash `tool_name` empty → case falls through → exit 0 (ALLOW). The reviewer sandbox silently permits the action if it can't parse the call.

**Target:** for a reviewer role (the `case` already gated at `:10-13`), an unparseable payload → exit 2 (deny), since we cannot prove the action is in-scope.

- [ ] **Step 1 — failing test.** `hooks/test_pre_reviewer_write.py` (script-style, matching `hooks/test_guard_destructive.py`): with `AUTO_PILOT_SUBAGENT_ROLE=codex-reviewer` + `AUTO_PILOT_OUTPUT_DIR=/tmp/ok`, feed malformed JSON (`not json`) and `{}` → assert exit code 2. Also a control: valid Edit inside the output dir → exit 0.
- [ ] **Step 2 — watch fail.** Run the script test → malformed-payload case returns 0 (FAIL, expected 2).
- [ ] **Step 3 — implement.** Change the tool_name extractor so a parse failure is distinguishable (e.g. print a sentinel `__PARSE_FAIL__` and `sys.exit(0)`); in bash, if `tool_name == __PARSE_FAIL__` for a reviewer role → `exit 2` with a BLOCKED message. Valid-but-unknown tool names still pass (only Edit/Write/MultiEdit/Bash are gated).
- [ ] **Step 4 — green.** Script test passes; `shellcheck hooks/pre-reviewer-write.sh` clean.
- [ ] **Step 5 — wire the new self-test into CI** (see Task C3) and commit. `Constraint: fail-closed only for reviewer roles; non-reviewer dispatch unaffected (early exit at :10-13).`

### Cluster A review gate
- [ ] Freeze `git diff` for cluster A → SHA-256 → dispatch `auto-pilot-codex-reviewer` + `auto-pilot-claude-reviewer`. Both must APPROVE; fix findings; re-review until 0 new. Commit any fix.

---

## Cluster B — Security / env

**Files:**
- Modify: `scripts/_reviewer_wrapper.py`
- Modify: `hooks/guard-destructive.py` (docstring only)
- Test: `tests/test_reviewer_wrapper.py` (create if absent)

### Task B1: reviewer env — allowlist, not denylist (audit #5)

Current bug (`scripts/_reviewer_wrapper.py:104-124`): `_reviewer_env` is allow-by-default (`{k:v for ... if k not in _ENV_DENYLIST}`) and the denylist omits this repo's actual secret var names (`GH_CLIENT_ID`, `GH_CLIENT_SECRET`, `GH_TOKEN`). If `.env` is sourced, those reach every `claude -p` reviewer subprocess.

**Decision:** keep the denylist approach but make it pattern-based AND closed against the repo's own names — deny any var whose name matches `(?i)(SECRET|TOKEN|PASSWORD|_KEY$|^GH_CLIENT|DATABASE_URL|REDIS_URL)`. (Full allowlist rejected: a reviewer subprocess needs PATH/HOME/LANG/TMPDIR/AUTO_PILOT_*/many incidental vars; an allowlist would be brittle and break the reviewer. Pattern-denylist closes the secret classes without that fragility.)

- [ ] **Step 1 — failing test.** `tests/test_reviewer_wrapper.py::test_reviewer_env_strips_secrets`:
```python
def test_reviewer_env_strips_secrets(monkeypatch, tmp_path):
    import _reviewer_wrapper as rw
    for k in ["GH_CLIENT_ID","GH_CLIENT_SECRET","GH_TOKEN","MY_API_TOKEN",
              "DB_PASSWORD","SOME_SECRET","STRIPE_KEY","GITHUB_TOKEN"]:
        monkeypatch.setenv(k, "leak")
    monkeypatch.setenv("PATH", "/usr/bin")  # must survive
    env = rw._reviewer_env("codex-reviewer", tmp_path)
    for k in ["GH_CLIENT_ID","GH_CLIENT_SECRET","GH_TOKEN","MY_API_TOKEN",
              "DB_PASSWORD","SOME_SECRET","STRIPE_KEY","GITHUB_TOKEN"]:
        assert k not in env, f"{k} leaked to reviewer env"
    assert env["PATH"] == "/usr/bin"
    assert env["AUTO_PILOT_SUBAGENT_ROLE"] == "codex-reviewer"
```
- [ ] **Step 2 — watch fail.** `GH_CLIENT_SECRET`, `GH_TOKEN`, `MY_API_TOKEN`, etc. leak (FAIL).
- [ ] **Step 3 — implement.** Replace the membership check with a compiled regex `_SECRET_RE = re.compile(r"(?i)(SECRET|TOKEN|PASSWORD|_KEY$|^GH_CLIENT|DATABASE_URL|REDIS_URL)")`; keep the existing literal `_ENV_DENYLIST` as an explicit floor (union of both). `env = {k:v for k,v in os.environ.items() if k not in _ENV_DENYLIST and not _SECRET_RE.search(k)}`.
- [ ] **Step 4 — green + mypy + ruff.**
- [ ] **Step 5 — commit.** `Rejected: full allowlist | brittle — reviewer needs many incidental vars (PATH/HOME/LANG/TMPDIR); pattern-denylist closes secret classes without breakage. Not-tested: a secret var not matching the pattern (e.g. opaque name) still passes — residual.`

### Task B2: guard-destructive — honest docstring (audit #6)

Finding: the guard is defeated by obfuscation (`echo … | base64 -d | sh`, `$R -rf`, `curl|sh`); the docstring overstates protection. Do NOT chase obfuscation (regex ceiling is architectural) — fix the framing.

- [ ] **Step 1.** Edit `hooks/guard-destructive.py` header docstring: state plainly it is a *best-effort literal-pattern* guard, NOT a sandbox; obfuscated/indirected commands (base64, var-indirection, `curl|sh`) are out of scope and pass; it is a speed-bump against accidental destructive ops, not an adversarial boundary. (No code/behavior change.)
- [ ] **Step 2.** `shellcheck`/tests unaffected; run `python3 hooks/test_guard_destructive.py` to confirm no regression.
- [ ] **Step 3 — commit.** `Constraint: regex-on-string cannot catch indirection without a command parser/sandbox (architectural limit, documented not fixed).`

### Cluster B review gate
- [ ] Freeze diff → dual review → APPROVE/0-new.

---

## Cluster C — Test rigor

**Files:**
- Modify: `tests/test_gc.py`
- Modify: `scripts/learning_miner.py`, `tests/test_learning_miner.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `CLAUDE.md` (swarm test-type wording, Task C4)

### Task C1: kill the unconditionally-true assertion (audit #7)

`tests/test_gc.py:42`: `assert (tickets / "worker.json") not in [Path(p) for p in removed] or True` — the `or True` makes it never fail. The ticket is old (7 days) + has no `done.marker` → it IS an orphan → `sweep_orphan_tickets` should remove it.

- [ ] **Step 1 — read the contract.** Read `_gc.sweep_orphan_tickets` to confirm its return = list of removed paths and that an old, marker-less ticket is removed.
- [ ] **Step 2 — replace the assertion** with the real one:
```python
removed_paths = [Path(p) for p in removed]
assert (tickets / "worker.json") in removed_paths, \
    "old marker-less ticket should be reaped as an orphan"
```
(If reading the contract shows it is *reported* not *removed*, assert the actual returned shape — but assert something that CAN fail.)
- [ ] **Step 3 — run.** `pytest tests/test_gc.py::test_sweep_orphan_tickets_removes_no_marker -v` must PASS for the real reason (flip the assertion to the wrong value once to confirm it can fail, then restore).
- [ ] **Step 4 — commit.** `Not-tested: n/a — this restores a real assertion.`

### Task C2: coerce non-string run_id → non-persisting (audit #8 — the gap deferred 2026-06-09)

`scripts/learning_miner.py:47` `current_run_id` does `str(data.get("run_id",""))`, so JSON `null`→`"None"` and numeric `0`→`"0"` are truthy → persist a `distinct_runs`-stuck ticket, defeating the empty-run_id guard for those shapes.

- [ ] **Step 1 — failing tests** in `tests/test_learning_miner.py`:
```python
def test_null_run_id_does_not_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    line = {"class": "fail-open", "issue": "x", "candidate_asset": "hook"}
    d = root / ".planning" / "auto-pilot"; d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": None}))
    with (d / "insights.jsonl").open("w") as f:
        f.write(json.dumps(line) + "\n")
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert _ledger_tickets(tmp_path / "home", root) == []

def test_numeric_run_id_does_not_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    line = {"class": "fail-open", "issue": "x", "candidate_asset": "hook"}
    d = root / ".planning" / "auto-pilot"; d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": 0}))
    with (d / "insights.jsonl").open("w") as f:
        f.write(json.dumps(line) + "\n")
    lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)
    assert _ledger_tickets(tmp_path / "home", root) == []
```
- [ ] **Step 2 — watch fail.** Both persist a ticket today (FAIL).
- [ ] **Step 3 — implement** in `current_run_id`:
```python
val = data.get("run_id", "")
if not isinstance(val, str):
    return ""          # null / numeric / list → no run identity
return val
```
(Keep the existing `.strip()` guard in `run_miner` for whitespace.)
- [ ] **Step 4 — green + full suite + mypy + ruff.**
- [ ] **Step 5 — commit.** `Constraint: only str run_id counts as identity; closes the 2026-06-09 deferred gap.`

### Task C3: CI-gate the hook self-tests (audit P2)

`hooks/test_*.py` (guard-destructive, codex-conductor-guard, notebooklm-delete-gate, + the new pre-reviewer-write from A3) run only by hand; a regression ships green.

- [ ] **Step 1.** Read `.github/workflows/ci.yml` to find the test job.
- [ ] **Step 2.** Add a step that runs every bundled hook self-test:
```yaml
      - name: Hook self-tests
        run: |
          python3 hooks/test_guard_destructive.py
          python3 hooks/test_codex_conductor_guard.py
          python3 hooks/test_notebooklm_delete_gate.py
          python3 hooks/test_pre_reviewer_write.py
```
- [ ] **Step 3.** Confirm locally each exits 0. Commit. `Not-tested: CI YAML change verified locally by running the commands; full CI run confirms on push.`

### Task C4: fix CLAUDE.md swarm test-type wording (audit P2)

`swarm/tests/` holds `*.sh`, not bats/pytest; CLAUDE.md's Testing section implies a runnable suite.

- [ ] **Step 1.** Edit the CLAUDE.md Testing block to state swarm tests are script-style `*.sh` (and either wire them into CI like C3 if they're self-contained, or mark them manual). Verify with `ls swarm/tests/`.
- [ ] **Step 2 — commit.**

### Cluster C review gate
- [ ] Freeze diff → dual review → APPROVE/0-new.

---

## Cluster D — Agent contracts

**Files:**
- Modify: `agents/retro.md`
- Modify: `agents/worker.md` + (optional) a new `hooks/worker-scope-gate.sh` + `hooks/hooks.json`
- Modify: `agents/specialist-pool.md`

### Task D1: retro — one canonical output-target list (audit #9)

`agents/retro.md` specifies its write surface three ways (§19 = 4 targets, §28 = 2, §51 = 2). An agent anchoring on §28 drops the `insights.jsonl` Hermes sidecar.

- [ ] **Step 1.** Read `agents/retro.md` §19/§28/§51. Define ONE canonical "Output targets" list (the full set: `.claude/insights.md` prose, `.planning/auto-pilot/insights.jsonl` Hermes sidecar, session-memory pointer, and — conditionally — vault `intent/gotchas/`). Make §28 and §51 *cite* the canonical list, not restate a partial one.
- [ ] **Step 2 — verify** no remaining section names a different/partial target set (`grep -n "insights" agents/retro.md`).
- [ ] **Step 3 — commit.**

### Task D2: retro — resolve "never edit source" vs ordered `docs/architecture.md` write (audit #10)

§19 says never edit source; §94 orders appending to `docs/architecture.md`, which `hooks/pre-edit-human-only.sh` (Tier-2) DENIES. The contract orders a blocked write.

- [ ] **Step 1.** Read `agents/retro.md:94` + `hooks/pre-edit-human-only.sh` Tier-2 list + the §98 `master-plan.md` "report instead" pattern.
- [ ] **Step 2.** Choose the consistent resolution: change retro to **report** the architecture.md distillation to the PM (matching the §98 pattern) rather than editing it directly. Edit §94 accordingly; remove the contradiction with §19.
- [ ] **Step 3 — verify** retro no longer instructs a Tier-2 write (`grep -n "architecture.md" agents/retro.md`). Commit. `Rejected: grant retro AUTO_PILOT_ALLOW_CORE_EDIT bypass | widens the human-only boundary for an automated agent — report-to-PM is safer and matches master-plan handling.`

### Task D3: worker scope-allowlist — edit-time enforcement (audit #11)

`agents/worker.md:13` claims out-of-scope edits "auto-REJECT" but nothing blocks them at edit time; only the reviewer detects after the fact.

**Decision:** add a PreToolUse(Edit|Write|MultiEdit) hook `hooks/worker-scope-gate.sh` that, when `AUTO_PILOT_SUBAGENT_ROLE=worker` and `AUTO_PILOT_SCOPE_FILES` (newline/space list) is set, denies an edit whose `file_path` is not in the scope list. (Mirrors the reviewer sandbox pattern in `pre-reviewer-write.sh`.) If the env contract is too invasive to thread now, downgrade to: tighten `agents/worker.md` wording to say "reviewer-detected, not edit-blocked" (honest) — pick the hook if the dispatch path can set the env, else the wording fix.

- [ ] **Step 1 — failing test.** `hooks/test_worker_scope_gate.py` (script-style): `AUTO_PILOT_SUBAGENT_ROLE=worker AUTO_PILOT_SCOPE_FILES="scripts/a.py"` + Edit to `scripts/b.py` → exit 2; Edit to `scripts/a.py` → exit 0; role unset → exit 0.
- [ ] **Step 2 — watch fail** (hook doesn't exist → script errors). 
- [ ] **Step 3 — implement** `hooks/worker-scope-gate.sh` (fail-closed on parse error for the worker role, per A3 precedent), `chmod +x`, wire into `hooks/hooks.json` PreToolUse Edit|Write|MultiEdit matcher.
- [ ] **Step 4 — green; `shellcheck`; wire self-test into CI (C3).** Update `agents/worker.md:13` to reference the gate as the enforcement (not just prose).
- [ ] **Step 5 — commit.** `Constraint: gate active only when the PM sets AUTO_PILOT_SCOPE_FILES in the worker env; absent → no-op (documented).`

### Task D4: specialist-pool — mark unported reviewers (audit P2)

`agents/specialist-pool.md` lists 4 Tier-2 reviewers with no agent file inline with live ones; a PM could dispatch a non-existent `subagent_type`.

- [ ] **Step 1.** Edit the mapping table to mark `database-reviewer`/`infra-reviewer`/`prompt-reviewer`/`test-quality-reviewer` with an explicit inline `— NOT YET PORTED, do not dispatch` marker.
- [ ] **Step 2 — commit.**

### Cluster D review gate
- [ ] Freeze diff → dual review → APPROVE/0-new.

---

## Cluster E — Docs / drift

**Files:**
- Modify: `scripts/docs/check_doc_reference_integrity.py`, `tests/test_doc_reference_integrity.py`
- Modify: `CLAUDE.md`, `scripts/quality/module_size_budget.txt`, `docs/onboarding/README.md`
- Fix the live WARN'd citations in `docs/`

### Task E1: symbol-WARN — test it, then fix the stale citations (audit #12, #13)

The symbol-proximity WARN heuristic (`check_doc_reference_integrity.py:290-311`) is untested and every current WARN is a false positive (symbol exists, line drifted). Two-part fix: (a) add tests for the WARN path so its behavior is pinned; (b) correct the stale `:line` citations so the WARN set goes to zero.

- [ ] **Step 1 — failing test.** `tests/test_doc_reference_integrity.py`: a fixture doc citing `foo.py:5` where symbol `foo` is at line 50 → assert a WARN is emitted (captured stderr / return structure); a doc citing the correct line → no WARN. (Watch fail — no such test today.)
- [ ] **Step 2 — implement/confirm** the WARN function behaves per the test (it likely already does; the test pins it). If the ±window is the issue, leave behavior, just pin it.
- [ ] **Step 3 — fix the live stale citations** the audit named: `docs/specs/2026-06-09-hermes-loop-mvp-design.md:54` (`pivot_detector` → correct line near `scripts/orchestrator.py:81`), and re-run `python3 scripts/docs/check_doc_reference_integrity.py` → iterate until **0 WARN, 0 violations**.
- [ ] **Step 4 — commit.** `Constraint: WARN stays advisory (not promoted to CI-fail) because line-drift churn is high; the test pins behavior and the live WARN set is now zero.`

### Task E2: stale prose in CLAUDE.md + onboarding + module-size budget (audit P2 ×3)

- [ ] **Step 1.** `CLAUDE.md:37` — replace `currently 2026-05-28-dogfood-smoke.md` with the actual `ls docs/specs/` set, or stop enumerating a volatile dir (prefer the latter: "active PR-input/dogfood specs under `docs/specs/`").
- [ ] **Step 2.** `scripts/quality/module_size_budget.txt:11` — remove the stale `skills/quality-eval/SKILL.md|620` entry (actual 258, under the 500 default). Re-run `bash scripts/quality/check-module-size.sh` → OK.
- [ ] **Step 3.** `docs/onboarding/README.md` — regenerate (or update `source_commit`) so it is not 66 commits stale; confirm all referenced paths still resolve.
- [ ] **Step 4 — commit** each as its own small commit.

### Cluster E review gate
- [ ] Freeze diff → dual review (claude reviewer sufficient for docs; codex optional) → APPROVE/0-new.

---

## Phase F — Re-audit & honest scoring

- [ ] **F1.** Re-run the six dimension auditors (read-only subagents) over the post-fix tree, seeded with the original findings + "verify each is closed; report any NEW finding the fixes introduced."
- [ ] **F2.** Re-run all gates: `pytest tests/ -q`, vault pytest, `mypy`, `ruff`, `shellcheck hooks/*.sh`, `check-module-size.sh`, `check_doc_reference_integrity.py` (target 0 WARN/0 violation), the ARL + setup-harness bats, the hook self-tests.
- [ ] **F3.** Produce the honest re-scorecard: per-dimension score, residual findings (architectural-limit only — e.g. regex-guard obfuscation ceiling, prose semantic drift no mechanical guard catches, single-string Bash-hook blast radius). **No "100/perfect/최종" verdict** — terminal honest state = "0 P0/P1 open; re-audit 0 new; residuals stated."
- [ ] **F4.** Update memory (`hermes-loop-mvp.md` or a new quality-campaign note) + commit; push to main + watch CI only on explicit deploy request.

---

## Self-review (plan vs audit)

- **Coverage:** every P1 (#1–#13) maps to a task — A1(#1,#2), A2(#3,#4), A3(reviewer-fail-open P2), B1(#5), B2(#6), C1(#7), C2(#8), D1(#9), D2(#10), D3(#11), E1(#12,#13). Meaningful P2s → C3/C4/D4/E1/E2. ✓
- **Behavior-change callout:** A1 + A2 change guard behavior for all sessions — flagged, landed first, fully test-covered. ✓
- **Placeholder scan:** all code steps carry real code or a reference algorithm + an exhaustive test table (the table IS the contract for the bash hooks). ✓
- **Type/name consistency:** `_SECRET_RE`, `_reviewer_env`, `current_run_id`, `_ledger_tickets`, `sweep_orphan_tickets` match their source definitions. ✓
- **Residual honesty:** B2/D3/E1 explicitly bound what is NOT fixed (regex ceiling, env-dependent gate, advisory WARN). ✓

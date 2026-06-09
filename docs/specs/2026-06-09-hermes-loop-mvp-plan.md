# Hermes-Loop MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (or executing-plans). Steps use checkbox (`- [ ]`) syntax. TDD: write the failing test FIRST, watch it fail, then implement.

**Goal:** A discover-only self-improvement layer that fingerprints recurring reviewer/doom-loop patterns, accumulates cross-run counts in a durable per-project ledger outside the target repo, and emits a `promotable`/`thin` gate verdict.

**Architecture:** Deterministic Python, no LLM, mirroring `scripts/risk_assess.py`. Two layers with a frozen interface so they implement in parallel: `_improvement.py` (identity + ticket I/O + lock + schema validation) and `learning_miner.py` (scan + gate + CLI). `retro` agent untouched.

**Tech Stack:** Python 3 stdlib + `jsonschema` (already a repo dep), `pytest`, `mypy`, `ruff`. JSON Schema 2020-12.

**Spec:** `docs/specs/2026-06-09-hermes-loop-mvp-design.md`. Read it first.

---

## Frozen interface (the contract between the two layers)

Both workers code against THIS. Do not change a signature without updating the plan.

```python
# scripts/_improvement.py  — public API

PLUGIN_VERSION: str  # read once from .claude-plugin/plugin.json "version"

def normalize_issue(text: str) -> str:
    """lowercase; collapse whitespace; strip abs/rel paths, line numbers,
    ISO-8601 dates, and a leading 'phase-N' token. Returns the canonical issue."""

def compute_fingerprint(source: str, file_basename: str, issue: str,
                        candidate_asset: str | None) -> str:
    """sha256 hex of source\x1f file_basename\x1f normalize_issue(issue)\x1f (candidate_asset or '')."""

def project_slug(repo_root: Path) -> str:
    """str(repo_root.resolve()).replace('/', '-')  — matches ~/.claude/projects/<slug> convention."""

def repo_fingerprint(repo_root: Path) -> str:
    """sha256(git remote get-url origin, else str(repo_root.resolve()))[:16]."""

def ledger_dir(repo_root: Path, commit_to: Path | None) -> Path:
    """commit_to if given, else Path.home()/'.claude'/'projects'/project_slug/'improvements'."""

def validate_ticket(obj: dict) -> None:
    """jsonschema-validate against schemas/improvement-ticket.schema.json. Raise jsonschema.ValidationError on fail."""

@dataclass(frozen=True)
class Observation:
    source: str            # 'reviewer-finding' | 'doom-loop'
    file_basename: str
    issue: str             # raw issue text (pre-normalize)
    candidate_asset: str | None
    run_id: str
    snippet: str           # self-contained evidence text (<=500 chars)

def bump_or_create(ledger: Path, obs: Observation, *, repo_root: Path,
                  now: datetime, dry_run: bool) -> dict:
    """flock + atomic temp+rename RMW of ledger/<fp>.json. fp = compute_fingerprint(...).
    repo_fingerprint is derived from repo_root (NOT ledger). dry_run creates no dir.
    A corrupt existing ticket is reseeded (no crash).
    evidence deduped on (run_id, snippet). occurrences = len(evidence).
    distinct_runs = len({e['run_id'] for e in evidence}).
    Create with state='candidate', first_seen=last_seen=now if absent; else last_seen=now.
    Returns the resulting ticket dict (PROJECTED in memory, NOT written, when dry_run)."""
```

```python
# scripts/learning_miner.py  — public API

PROMOTION_THRESHOLDS: dict[str, int]  # {'reviewer-finding': 2, 'doom-loop': 3, 'pivot': 3, 'wasted-tool': 3, 'insight': 3}

def scan_reviewer_findings(repo_root: Path, run_id: str) -> list[Observation]:
    """parse .planning/auto-pilot/critic-rejections-phase-*.jsonl → Observations (source='reviewer-finding')."""

def scan_doom_loops(repo_root: Path, run_id: str) -> list[Observation]:
    """parse .planning/auto-pilot/state.json pivot_detector buckets (value>=1) → Observations (source='doom-loop')."""

def current_run_id(repo_root: Path) -> str:
    """state.json 'run_id'; '' if absent. All observations from one .planning share it (re-scan idempotent)."""

def verdict_for(tickets: list[dict]) -> str:
    """'promotable' if any ticket has distinct_runs >= PROMOTION_THRESHOLDS[ticket['source']], else 'thin'."""

def run_miner(repo_root: Path, *, commit_to: Path | None, now: datetime,
             dry_run: bool) -> dict:
    """scan → bump each observation → collect resulting tickets → verdict.
    Returns {'verdict','candidates','promotable_count','by_asset'}."""

def main(argv: list[str] | None = None) -> int:
    """argparse CLI. Exit 0 always unless --fail-on promotable and verdict==promotable → 2."""
```

---

## Task 1: improvement-ticket schema  (Worker A)

**Files:**
- Create: `schemas/improvement-ticket.schema.json`
- Test: `tests/test_improvement.py` (schema cases)

- [ ] **Step 1: Write failing schema-validation tests**

```python
# tests/test_improvement.py
import json, subprocess, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "improvement-ticket.schema.json"

def _valid_ticket():
    return {
        "schema_version": 1,
        "fingerprint": "a" * 64,
        "state": "candidate",
        "pattern": "missing verify evidence",
        "source": "reviewer-finding",
        "candidate_asset": "hook",
        "occurrences": 1,
        "distinct_runs": 1,
        "first_seen": "2026-06-09T00:00:00Z",
        "last_seen": "2026-06-09T00:00:00Z",
        "plugin_version": "0.8.7",
        "repo_fingerprint": "abc123",
        "evidence": [{"run_id": "r1", "snippet": "reviewer said X"}],
        "promotion_gate": {"tests_pass": None, "ci_pass": None, "user_approved": None},
    }

def _validate(obj):
    import _improvement
    _improvement.validate_ticket(obj)

def test_valid_ticket_passes():
    _validate(_valid_ticket())

def test_extra_property_rejected():
    import jsonschema
    t = _valid_ticket(); t["bogus"] = 1
    with pytest.raises(jsonschema.ValidationError):
        _validate(t)

def test_bad_state_rejected():
    import jsonschema
    t = _valid_ticket(); t["state"] = "nope"
    with pytest.raises(jsonschema.ValidationError):
        _validate(t)

def test_short_fingerprint_rejected():
    import jsonschema
    t = _valid_ticket(); t["fingerprint"] = "abc"
    with pytest.raises(jsonschema.ValidationError):
        _validate(t)

def test_empty_evidence_rejected():
    import jsonschema
    t = _valid_ticket(); t["evidence"] = []
    with pytest.raises(jsonschema.ValidationError):
        _validate(t)
```

- [ ] **Step 2: Run, verify fail** — `python3 -m pytest tests/test_improvement.py -k schema -q` → FAIL (no `_improvement` / no schema).

- [ ] **Step 3: Write the schema**

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://auto-pilot/improvement-ticket/v1",
  "type": "object",
  "required": ["schema_version", "fingerprint", "state", "pattern", "source",
               "candidate_asset", "occurrences", "distinct_runs", "first_seen",
               "last_seen", "plugin_version", "repo_fingerprint", "evidence",
               "promotion_gate"],
  "properties": {
    "schema_version":  { "const": 1 },
    "fingerprint":     { "type": "string", "pattern": "^[a-f0-9]{64}$" },
    "state":           { "enum": ["candidate","accepted","implemented","verified","promoted","rejected"] },
    "pattern":         { "type": "string", "minLength": 1 },
    "source":          { "enum": ["reviewer-finding","doom-loop","pivot","insight","wasted-tool"] },
    "candidate_asset": { "enum": ["skill","hook","schema","test","doc","cache", null] },
    "occurrences":     { "type": "integer", "minimum": 1 },
    "distinct_runs":   { "type": "integer", "minimum": 1 },
    "first_seen":      { "type": "string", "format": "date-time" },
    "last_seen":       { "type": "string", "format": "date-time" },
    "plugin_version":  { "type": "string" },
    "repo_fingerprint":{ "type": "string", "minLength": 1 },
    "evidence": {
      "type": "array", "minItems": 1,
      "items": {
        "type": "object",
        "required": ["run_id", "snippet"],
        "properties": {
          "run_id":      { "type": "string" },
          "snippet":     { "type": "string" },
          "source_path": { "type": "string" },
          "locator":     { "type": "string" }
        },
        "additionalProperties": false
      }
    },
    "promotion_gate": {
      "type": "object",
      "required": ["tests_pass","ci_pass","user_approved"],
      "properties": {
        "tests_pass":    { "type": ["boolean","null"] },
        "ci_pass":       { "type": ["boolean","null"] },
        "user_approved": { "type": ["boolean","null"] }
      },
      "additionalProperties": false
    },
    "notes": { "type": "string" }
  },
  "additionalProperties": false
}
```

- [ ] **Step 4: Run, verify pass** — `python3 -m pytest tests/test_improvement.py -k schema -q` → PASS.
- [ ] **Step 5: Commit** — `git add schemas/improvement-ticket.schema.json tests/test_improvement.py && git commit -m "feat(schema): improvement-ticket record"`

## Task 2: _improvement.py identity + I/O  (Worker A)

**Files:** Create `scripts/_improvement.py`; extend `tests/test_improvement.py`.

- [ ] **Step 1: Write failing tests** (fingerprint stability/collision, bump semantics, lock)

```python
# append to tests/test_improvement.py
from datetime import datetime, timezone
import _improvement as imp
from _improvement import Observation

NOW = datetime(2026, 6, 9, tzinfo=timezone.utc)

def test_fingerprint_stable_across_line_path_date():
    a = imp.compute_fingerprint("reviewer-finding", "auth.py",
        "phase-2 /Users/x/auth.py:88 missing token check 2026-06-09", "hook")  <!-- cite-ignore -->  fixture, not a repo citation
    b = imp.compute_fingerprint("reviewer-finding", "auth.py",
        "phase-5 /tmp/auth.py:120 missing token check 2026-01-01", "hook")  <!-- cite-ignore -->  fixture, not a repo citation
    assert a == b  # line/path/date/phase normalized away

def test_fingerprint_distinguishes_semantics():
    a = imp.compute_fingerprint("reviewer-finding", "a.py", "missing token check", "hook")
    b = imp.compute_fingerprint("reviewer-finding", "a.py", "unbounded recursion in parser", "hook")
    assert a != b  # full issue kept, no 8-token truncation collision

def test_bump_new_run_increments_distinct(tmp_path):
    obs1 = Observation("reviewer-finding","a.py","missing token check","hook","r1","snip-a")
    obs2 = Observation("reviewer-finding","a.py","missing token check","hook","r2","snip-b")
    t1 = imp.bump_or_create(tmp_path, obs1, now=NOW, dry_run=False)
    t2 = imp.bump_or_create(tmp_path, obs2, now=NOW, dry_run=False)
    assert t2["occurrences"] == 2 and t2["distinct_runs"] == 2

def test_same_run_retrip_keeps_distinct_one(tmp_path):
    obs1 = Observation("reviewer-finding","a.py","missing token check","hook","r1","snip-a")
    obs2 = Observation("reviewer-finding","a.py","missing token check","hook","r1","snip-b")
    imp.bump_or_create(tmp_path, obs1, now=NOW, dry_run=False)
    t = imp.bump_or_create(tmp_path, obs2, now=NOW, dry_run=False)
    assert t["occurrences"] == 2 and t["distinct_runs"] == 1

def test_rescan_is_idempotent(tmp_path):
    obs = Observation("reviewer-finding","a.py","missing token check","hook","r1","snip-a")
    imp.bump_or_create(tmp_path, obs, now=NOW, dry_run=False)
    t = imp.bump_or_create(tmp_path, obs, now=NOW, dry_run=False)  # identical (run_id,snippet)
    assert t["occurrences"] == 1 and t["distinct_runs"] == 1

def test_dry_run_writes_nothing(tmp_path):
    obs = Observation("reviewer-finding","a.py","x issue","hook","r1","snip")
    imp.bump_or_create(tmp_path, obs, now=NOW, dry_run=True)
    assert list(tmp_path.glob("*.json")) == []

def test_bumped_ticket_is_schema_valid(tmp_path):
    obs = Observation("reviewer-finding","a.py","missing token check","hook","r1","snip")
    t = imp.bump_or_create(tmp_path, obs, now=NOW, dry_run=False)
    imp.validate_ticket(t)
```

- [ ] **Step 2: Run, verify fail** — `python3 -m pytest tests/test_improvement.py -q` → FAIL.

- [ ] **Step 3: Implement `scripts/_improvement.py`** against the frozen interface. Key points:
  - `PLUGIN_VERSION` from `.claude-plugin/plugin.json` (walk up from `__file__`; fallback `"0"`).
  - `normalize_issue`: regex strip `phase-\d+`, paths (`(/[\w.-]+)+`), `:\d+` line refs, ISO dates (`\d{4}-\d{2}-\d{2}(T[\d:]+Z?)?`); lowercase; `" ".join(split())`.
  - fingerprint via `hashlib.sha256(("\x1f".join([...])).encode()).hexdigest()`.
  - `bump_or_create`: build fp, path = `ledger/<fp>.json`; read existing (or seed new); evidence list; dedup on `(run_id, snippet)`; `occurrences=len(evidence)`; `distinct_runs=len({run_ids})`; `pattern=normalize_issue(obs.issue)`; `repo_fingerprint`/`plugin_version` stamped; validate before write; if not dry_run write via flock + atomic temp+rename (reuse the `_state.py`/`_contract.py` pattern — `import` their helper if exposed, else replicate: write `tmp`, `os.replace`, hold an `fcntl.flock` on a `<fp>.json.lock`).
  - No bare `datetime.now()` — caller passes `now`.

- [ ] **Step 4: Run, verify pass** — `python3 -m pytest tests/test_improvement.py -q` → PASS.
- [ ] **Step 5: parallel-bump test + commit**

```python
def test_parallel_bump_no_lost_update(tmp_path):
    import concurrent.futures as cf
    def one(i):
        obs = Observation("reviewer-finding","a.py","missing token check","hook",f"r{i}",f"s{i}")
        return imp.bump_or_create(tmp_path, obs, now=NOW, dry_run=False)
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        list(ex.map(one, range(8)))
    import json
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    t = json.loads(files[0].read_text())
    assert t["distinct_runs"] == 8  # all 8 runs counted, none lost
```
Run `-q` → PASS. `git add scripts/_improvement.py tests/test_improvement.py && git commit -m "feat: improvement ticket identity + locked ledger I/O"`

## Task 3: learning_miner.py scan + gate + CLI  (Worker B — codes against frozen interface)

**Files:** Create `scripts/learning_miner.py`; create `tests/test_learning_miner.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_learning_miner.py
import json, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import learning_miner as lm

NOW = datetime(2026, 6, 9, tzinfo=timezone.utc)

def _planning(tmp_path, run_id, findings):
    d = tmp_path / ".planning" / "auto-pilot"; d.mkdir(parents=True)
    (d / "state.json").write_text(json.dumps({"run_id": run_id, "pivot_detector": {}}))
    with (d / "critic-rejections-phase-1.jsonl").open("w") as f:
        for fi in findings:
            f.write(json.dumps(fi) + "\n")
    return tmp_path

def test_reviewer_two_distinct_runs_promotable(tmp_path, monkeypatch):
    home = tmp_path / "home"; monkeypatch.setenv("HOME", str(home))
    f = [{"file": "a.py", "line": 10, "issue": "missing token check", "candidate_asset": "hook"}]
    _planning(tmp_path / "run1", "r1", f); _planning(tmp_path / "run2", "r2", f)
    lm.run_miner(tmp_path / "run1", commit_to=None, now=NOW, dry_run=False)
    r = lm.run_miner(tmp_path / "run2", commit_to=None, now=NOW, dry_run=False)
    # SAME repo? No — different roots → different slug. Use one root, two scans w/ diff run_id:
    # (see test_same_root_two_runs below for the real promotion path)

def test_same_root_two_runs_promotable(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    f = [{"file": "a.py", "line": 10, "issue": "missing token check", "candidate_asset": "hook"}]
    # run 1
    (root / ".planning" / "auto-pilot").mkdir(parents=True)
    (root / ".planning/auto-pilot/state.json").write_text(json.dumps({"run_id": "r1"}))
    (root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl").write_text(json.dumps(f[0]) + "\n")
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"
    # run 2 (new run_id, same finding)
    (root / ".planning/auto-pilot/state.json").write_text(json.dumps({"run_id": "r2"}))
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "promotable"

def test_empty_inputs_thin_no_crash(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"; root.mkdir()
    assert lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"] == "thin"

def test_dry_run_verdict_matches_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"
    (root / ".planning/auto-pilot").mkdir(parents=True)
    (root / ".planning/auto-pilot/state.json").write_text(json.dumps({"run_id": "r1"}))
    (root / ".planning/auto-pilot/critic-rejections-phase-1.jsonl").write_text(
        json.dumps({"file": "a.py", "line": 1, "issue": "x", "candidate_asset": None}) + "\n")
    dry = lm.run_miner(root, commit_to=None, now=NOW, dry_run=True)["verdict"]
    wet = lm.run_miner(root, commit_to=None, now=NOW, dry_run=False)["verdict"]
    assert dry == wet

def test_fail_on_exit_codes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = tmp_path / "repo"; root.mkdir()
    assert lm.main(["--repo-root", str(root), "--fail-on", "promotable"]) == 0
```

- [ ] **Step 2: Run, verify fail** — `python3 -m pytest tests/test_learning_miner.py -q` → FAIL.

- [ ] **Step 3: Implement `scripts/learning_miner.py`**:
  - `import _improvement as imp`. `PROMOTION_THRESHOLDS` dict.
  - `current_run_id` reads `state.json["run_id"]` (`""` if missing/unparseable).
  - `scan_reviewer_findings`: glob `critic-rejections-phase-*.jsonl`; per line → `Observation(source="reviewer-finding", file_basename=basename(file), issue=issue, candidate_asset=…, run_id=run_id, snippet=json.dumps(finding)[:500])`. Tolerate missing keys.
  - `scan_doom_loops`: `state.json["pivot_detector"]` dict; for each `phase_key,count` with count≥1 emit one Observation (`source="doom-loop"`, file_basename=phase_key stripped, issue=the finding-hash/text, snippet). Tolerate absence.
  - `run_miner`: resolve run_id, gather observations, `bump_or_create` each into `imp.ledger_dir(root, commit_to)` (mkdir parents), collect returned tickets, `verdict = verdict_for(tickets)`, build `by_asset` counts, return dict. (Dry-run: pass through; projected tickets still computed for the verdict.)
  - `main`: argparse (`--repo-root` default `.`, `--commit-to`, `--dry-run`, `--fail-on {promotable}`, `--json`); build `now=datetime.now(timezone.utc)` HERE (entry point only); print report + one-line JSON; return `2` if `--fail-on promotable and verdict==promotable` else `0`. `if __name__=='__main__': raise SystemExit(main())`.

- [ ] **Step 4: Run, verify pass** — `python3 -m pytest tests/test_learning_miner.py -q` → PASS.
- [ ] **Step 5: Commit** — `git add scripts/learning_miner.py tests/test_learning_miner.py && git commit -m "feat: learning_miner scan + gate + CLI"`

## Task 4: integration hardening + full verify  (PM)

**Files:** maybe `scripts/quality/module_size_budget.txt`; CLI smoke.

- [ ] **Step 1: Full suite** — `python3 -m pytest tests/ -q` → all pass.
- [ ] **Step 2: Types + lint** — `python3 -m mypy scripts/ hooks/ && python3 -m ruff check scripts/ tests/ hooks/` → clean. Fix any finding.
- [ ] **Step 3: Module size** — `bash scripts/quality/check-module-size.sh`. If `_improvement.py`/`learning_miner.py` > 500, split or register in `scripts/quality/module_size_budget.txt` with a reason comment.
- [ ] **Step 4: CLI smoke** — `python3 scripts/learning_miner.py --repo-root . --dry-run --json` → prints `{"verdict":"thin",...}`, exit 0. `--fail-on promotable` on a thin repo → exit 0.
- [ ] **Step 5: Commit** — `git commit -am "test: hermes-loop full verify green"` (only if changes).

---

## Self-review (plan vs spec)

- Spec §4.1 ledger home → Task 2 `ledger_dir` (home default, `--commit-to` opt-in). ✓
- §4.2 fingerprint (no truncation, strip line/path/date/phase) → Task 2 `normalize_issue`/`compute_fingerprint` + tests `test_fingerprint_*`. ✓
- §4.3 two inputs, insights.md dropped → Task 3 `scan_reviewer_findings`+`scan_doom_loops` only. ✓
- §4.4 self-contained evidence (snippet, run_id) → Observation.snippet + evidence dedup. ✓
- §4.5 flock+atomic + validate-before-write → Task 2 Step 3 + `test_parallel_bump_no_lost_update`. ✓
- §5 schema (lineage fields, distinct_runs) → Task 1. ✓
- §6 CLI (dry-run parity, fail-on, injected now) → Task 3 + `test_dry_run_verdict_matches_persist`,`test_fail_on_exit_codes`. ✓
- §7 gate on distinct_runs → `verdict_for` + `test_same_root_two_runs_promotable`. ✓
- §8 TDD matrix → Tasks 1–3 tests. ✓ (`test_reviewer_two_distinct_runs_promotable` is a scaffold note, not a real assertion — the real promotion path is `test_same_root_two_runs_promotable`; delete the scaffold during impl.)
- §9 repo_fingerprint stability → Task 2 `repo_fingerprint` (git remote else abspath). Slug-collision documented in spec. ✓
```

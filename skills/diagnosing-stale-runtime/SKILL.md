---
name: diagnosing-stale-runtime
description: Use before claiming a file/class/function is dead or alive, when source code and runtime behavior disagree, when "removed" code still appears in output, when restart doesn't fix it, when prompt/template/config change isn't taking effect, when cache seems stale, when investigating two-process races, or when comparing handoff/memory claims to current code state. Map of universal checks for runtime-vs-source mismatch.
---

# Map

## Alive or dead?
| Question | Check |
|---|---|
| Still called? | `grep -rn 'name(' src --include='*.py'` exclude tests. 0 caller = dead. |
| Class still used? | Class in MRO ≠ method invoked. Check call sites, not definition. |
| Really deleted? | Stub with same signature is not deletion. Verify body, not name. |
| Memory/handoff says "removed"? | Verify on disk + verify caller count. Docs drift; code is authoritative. |

## Source disagrees with runtime — order
1. Find process (`ps -ef`, parent, start time, cwd, cmdline).
2. File mtime vs process start time. File-after-start = stale in memory.
3. Trace metadata: `extra.trace.raw_*` vs `extra.trace.post_*` shows which stage diverged.
4. `@lru_cache` / module-level singletons / registry decorators / `import` side effects freeze at first call.
5. `>1` writer to same target without lock = silent overwrite.
6. **Form hypothesis only after 1–5.**

## Symptom → first check
| Symptom | Check |
|---|---|
| DB row has old version label | `extra.schema_version` + `extra.prompt_version` BEFORE blaming code |
| "Restart didn't fix it" | Restart raced with file rewrite — mtime vs process start |
| Cache stale across iteration | `@lru_cache` without per-iter `cache_clear()` |
| Two writers race | `flock` per key, or DB unique index. Cross-host needs DB-level. |
| Removed function appears in trace | Stub vs delete. Inspect body, not name. |
| Output corrupted | Search trace for `raw_*` / `pre_*` vs `post_*` / `final_*` snapshot pairs. Diff = mutating stage. |
| Prompt rule not effective | Process imported pre-change version; cache_clear or full restart |
| Some matches clean, some broken in same minute | Two processes, no lock, both writing |

## N=1 LLM smoke is noise
- Single-run delta < ~40% at temperature ≥ 0.7 = drift, not signal.
- Require ≥2 consecutive runs before declaring success or regression on prompt/model change.

## Production change verification
- After deploy: query the FIRST data point produced by the running process. Compare its trace metadata against expected. Disk state ≠ runtime state.
- Restart alone proves nothing. Verify by *next emitted artifact*.

## Stub vs delete
| | Stub | Delete |
|---|---|---|
| Signature | kept | removed |
| Body | neutered (no-op / pass-through) | removed |
| Caller imports | still work | fail |
| Future reactivation risk | yes (one typo) | no |
| Audit rule | check body + caller count + MRO inheritance | check `git log -- path` |

## Trace fields worth searching when output looks wrong
- `raw_*_preview`, `pre_*`, `unprocessed_*`, `input_*` — pre-pipeline snapshot
- `post_*_preview`, `final_*`, `processed_*`, `output_*` — post-pipeline snapshot
- `*_version`, `schema_*`, `prompt_*`, `model_*` — what code/config was active
- Diff raw vs processed → identifies mutating stage

## Process-restart mechanics
- `@lru_cache(maxsize=N)` on file-reading functions: frozen at first call. Survives across requests within process. Cleared only by `cache_clear()` or process exit.
- Editable install (`pip install -e .`) `.pth` adds path to `sys.path`. Same dir as cwd usually. Verify with `cat .venv/lib/python*/site-packages/__editable__.*.pth`.
- PM2/supervisord auto-respawn: child PID changes, parent stays. `kill <child>` triggers respawn from current disk state.
- Race: `git pull && pm2 restart` ordering matters. If pm2 restart fires before git checkout finishes writing, new process imports old files.

## Two-process write race (silent overwrite)
- UPSERT without unique constraint + no app-level lock = both writes succeed, last wins.
- Per-key `fcntl.flock` on lockfile under `/tmp/<app>-locks/` covers same-host. Cross-host needs DB-level (advisory lock or unique constraint).
- OS releases `flock` on process exit — crash-safe.

## Handoff doc vs code
- Handoff/memory claim = "true at write time, possibly stale now".
- Before acting on "X was removed/added/changed":
  - Read the file.
  - Grep callers.
  - `git log -- <path>` for last touch.
- Code is authoritative for present-tense facts. Docs are authoritative for *why*.

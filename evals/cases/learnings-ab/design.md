# Port-boundary design note — learning-loop → Archon PoC

> Task 1 of `docs/specs/2026-06-20-learning-loop-archon-port.md`. Records the load-bearing
> port-boundary facts with `file:line` citations re-verified against the real source on
> 2026-06-20 (line numbers below are the ones that actually resolve — they differ from the
> spec's quoted numbers in a few places, noted inline). Two repos:
> auto-pilot (`/Users/lyan/Documents/Project/auto-pilot`, durable Python) and
> archon (`/Users/lyan/Documents/Project/archon`, the YAML engine, local clone — never committed).
>
> Conservative framing: this PoC is valid ONLY under the same-host / shared-`$HOME` /
> pinned-repo-root precondition stated at the end. Multi-container is a KNOWN GAP, not a
> solved problem.

## (a) Archon has no non-opt-in cross-run memory — `persist_sessions` MUST be off

The cross-model REVIEW step ports to Archon as pure YAML, but MINE/PROMOTE/INJECT cannot,
because Archon exposes no *durable, default-on* cross-run channel. Verified:

- **Per-run artifacts only.** The fallback artifacts dir is scoped to the run id:
  `archon/packages/workflows/src/executor.ts:257`
  → `artifactsDir: join(cwd, '.archon', 'artifacts', 'runs', workflowRunId)`.
  Nothing under `runs/<workflowRunId>/` survives as shared state across a *different* run.

- **The only cross-run channel is opt-in session persistence**, and `context: fresh` bypasses it:
  - `archon/packages/workflows/src/dag-executor.ts:3302`
    → `const bypassesPersistence = node.context === 'fresh';`
    (the explanatory comment is at `dag-executor.ts:3299`: *"`bypassesPersistence`
    (context:'fresh' only) also disables cross-run `persist_session`"*).
    Spec quoted `:3299`; the executable line is `:3302`.
  - When persistence IS active, the prior provider session is loaded from the DB store at
    `archon/packages/workflows/src/dag-executor.ts:3325`
    → `const persisted = await deps.store.getWorkflowNodeSession({...})`, gated by
    `if (persistScopeKey)` at `:3323`. Spec quoted `:3323`; the actual DB-resume call is `:3325`.
  - Persistence is **strictly opt-in** — off unless a node sets `persist_session` or the
    workflow sets `persist_sessions`: `dag-executor.ts:3307-3310`
    (`effectivePersist = nodePersistFlag ?? workflowPersistSessions`).

- **The opt-in flags themselves:**
  - workflow-level: `archon/packages/workflows/src/schemas/workflow.ts:93`
    → `persist_sessions: z.boolean().optional()`. (Spec quoted `workflow.ts:89`; the real
    line in `schemas/workflow.ts` is `:93`.)
  - node-level: `archon/packages/workflows/src/schemas/dag-node.ts:196`
    → `persist_session: z.boolean().optional()` (field doc-comment begins at `:191`).
    (Spec quoted `dag-node.ts:191`; the field declaration is `:196`.)

**Consequence for the A/B.** The reviewer node is pinned `context: fresh` and the workflow
sets NO `persist_sessions`. This guarantees both arms start from an identical blank session
so the only differing bit is the injected `learnings.md` content. The driver additionally
asserts no `node_session_resumed` event in either arm. The ONLY durable cross-run channel
this PoC relies on is the filesystem ledger at a stable path (section (c)).

## (b) `$WORKFLOW_ID` is per-run TEXT substitution — never a run_id

Archon substitutes `$WORKFLOW_ID` into prompt/command strings as plain text:
`archon/packages/workflows/src/executor-shared.ts:441`
→ `.replace(/\$WORKFLOW_ID/g, workflowId)`.

It is a per-run identifier injected by string replacement, with NO semantic tie to the
reviewed work unit. Using it as the learning-loop `run_id` would inflate `distinct_runs`
on same-diff re-runs (each Archon invocation = a new `$WORKFLOW_ID` even on a byte-identical
diff). The promotion gate counts distinct run_ids:
`auto-pilot/scripts/_improvement.py:314`
→ `ticket["distinct_runs"] = len({e["run_id"] for e in evidence})`,
and the miner credits each finding to the line's OWN run_id, not the live state run_id:
`auto-pilot/scripts/learning_miner.py:162-167` (`line_run_id = finding.get("run_id")`,
falling back to `_LEGACY_RUN_ID`, deliberately NOT the state run_id — see the inflation
warning comment at `:156-161`).

**Rule:** `run_id` derives from the reviewed work unit — `git rev-parse HEAD` on a clean
tree, fallback `shasum(diff.patch)` — emitted by `run_id_from_diff.sh` (Task 2).
`$WORKFLOW_ID` is for logging only.

## (c) Ledger slug embeds the absolute repo path → Archon worktree isolation diverges it

The durable ledger lives at `~/.claude/projects/<slug>/improvements/<fp>.json`:
`auto-pilot/scripts/_improvement.py:118-122`
→ `ledger_dir(repo_root, commit_to)`; with `commit_to=None` it returns
`Path.home() / ".claude" / "projects" / project_slug(repo_root) / "improvements"` (`:122`).

`<slug>` embeds the ABSOLUTE, resolved repo/worktree path:
`auto-pilot/scripts/_improvement.py:98,100`
→ `def project_slug(repo_root)` returns `str(repo_root.resolve()).replace("/", "-")`.
(Spec cited `:98,122`; the path-mangling line is `:100`, used by `ledger_dir` at `:122`.)

Archon's CLI **defaults to timestamped worktree isolation**, which changes the repo path
every run:
- default-on isolation: `archon/packages/cli/src/commands/workflow.ts:513`
  → comment *"Default to worktree isolation unless --no-worktree or --resume"*, with the
  decision computed at `:519-521` (`wantsIsolation`).
- worktree create gate: `archon/packages/cli/src/commands/workflow.ts:717`
  → `if (wantsIsolation && codebase) {`, branch name auto-generated as
  `` `${workflowName}-${Date.now()}` `` (`:719`) — a fresh timestamped path each run.
- creation call: `archon/packages/cli/src/commands/workflow.ts:780`
  → `const isolatedEnv = await provider.create({...})`.

Each timestamped worktree resolves to a DIFFERENT `repo_root.resolve()` → a DIFFERENT
`project_slug` → a DIFFERENT ledger dir. Same `$HOME` is NOT sufficient; the ledger would
diverge per run and `distinct_runs` would never accumulate.

**Pin (required):** the workflow YAML sets `worktree.enabled: false` (Archon honors this and
runs in the live checkout — `archon/packages/cli/src/commands/workflow.ts:486-487`,
`pinnedEnabled === false` → live checkout; `:519-521` lets the pinned policy override the
flag default), AND both the mine and inject commands pass a stable canonical `--repo-root`
so every run resolves the same `project_slug` and therefore the same ledger dir. The inject
side additionally reads that durable ledger via a new `--ledger-dir` override (Task 4), since
`resolve-learnings` otherwise always computes `ledger_dir(repo_root, None)`.

The host-local advisory lock that protects the ledger RMW is `fcntl.LOCK_EX` held across the
whole read-modify-write: `auto-pilot/scripts/_improvement.py:153-167` (`ledger_lock`). This
is process-local and host-local — the basis of the multi-container KNOWN GAP below.

## (d) Miner dry-run gate — forces no-write unless a real run_id is present

`run_miner` reads the live run_id and silently degrades to dry-run (NO ledger write) when it
is empty, even if the JSONL lines themselves carry a run_id:
- `auto-pilot/scripts/learning_miner.py:297`
  → `run_id = current_run_id(repo_root)` (reads `.planning/auto-pilot/state.json` `run_id`,
  returns `""` if absent — `current_run_id` at `learning_miner.py:69-76`).
- `auto-pilot/scripts/learning_miner.py:303`
  → `effective_dry_run = dry_run or (not run_id.strip())`; the `:304-305` branch emits
  `learning_miner.non_persisting reason=empty_run_id`.

**Consequence.** The mine node MUST establish a non-empty `run_id` BEFORE invoking the miner —
either by writing `.planning/auto-pilot/state.json {run_id: RUN_ID}` first, or via a new
`--run-id` flag (Task 3, the spec's PM default). The Task 3 test asserts a PHYSICAL ledger
file is created/bumped (proving the gate was satisfied), and that the same input WITHOUT the
flag/state stays dry-run (regression proof the gate is still load-bearing).

## (e) Render spoiler hazard — verbatim injection names the defect

`render_learnings` prints the ticket `pattern` and an evidence sample (run_id + snippet):
- `auto-pilot/scripts/_learnings.py:176` — start of the rendered `lines` list; the ticket
  `pattern` is emitted into the section header at `:191,194`
  (`pattern = str(ticket.get("pattern", ...))` → `f"## \`{fp}\` — {pattern[:80]}"`).
- `auto-pilot/scripts/_learnings.py:199` — `"**Evidence sample:**"`, immediately followed by
  `_fmt_evidence(ticket)` (`:200`), which prints `run \`{run_id}\`: {snippet[:120]}`
  (`_fmt_evidence` at `_learnings.py:149-163`, snippet emit at `:160`).

If injected verbatim into the reviewer prompt, this NAMES the defect (pattern text + evidence
snippet + run_id), so the A/B would measure "the prompt told the reviewer the answer," not
durable learning. **PoC requirement:** a new `--sanitized` render mode (Task 5) that keeps
selection (gate + scope-match, unchanged) but renders ONLY a generic class-level nudge —
NO issue title, NO evidence string, NO file path, NO line number, NO run id, NO snippet.
The oracle scores a catch only when a finding's `class == golden` AND its `file` matches the
hidden golden-defect file (location match, not class-anywhere), so a generic class nudge
cannot trivially win.

## Precondition (under which this PoC is valid)

- **Same host, shared `$HOME`.** The durable channel is `~/.claude/projects/<slug>/improvements/`
  on one machine. The lock is `fcntl` advisory + host-local (`_improvement.py:160`).
- **Pinned repo-root.** `worktree.enabled: false` in the YAML + a stable canonical
  `--repo-root` on every mine and inject command, so all runs resolve the SAME `project_slug`
  → the SAME ledger dir. Without this pin Archon's default timestamped worktree
  (`workflow.ts:513,717-719,780`) diverges the slug and the loop silently never accumulates.
- **Clean-session arms.** Reviewer node `context: fresh`, no `persist_sessions`; the only
  differing bit between arms is `learnings.md` content (sanitized real vs `_BLIND_MARKER`).

## KNOWN GAP — multi-container / multi-host

The ledger is a filesystem path under a single `$HOME`, guarded by a host-local `fcntl`
advisory lock (`_improvement.py:153-167`), and keyed by the absolute repo path
(`_improvement.py:98,100`). Across containers or hosts:
- each container has its own `$HOME` → a different `~/.claude/projects/...` tree → no shared ledger;
- even with a shared volume, `fcntl` advisory locks do not coordinate reliably across
  container/network filesystem boundaries;
- the absolute-path slug diverges per mount point.

A real multi-container deployment needs a server-mediated ledger (e.g. Postgres / a ledger
service) before this loop is shippable. That is explicitly OUT OF SCOPE for the measurement
PoC and is recorded as Unresolved fork #2 in the spec — make-or-break for production, not for
proving the thesis on one host.

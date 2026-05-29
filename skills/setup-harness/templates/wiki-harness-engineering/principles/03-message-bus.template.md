---
type: harness-pattern
pattern: file-message-bus
generated: {{DATE}}
---

# Pattern — File-Based Message Bus

> Stateful coordination between PM and N workers using only the local filesystem. No daemon, no broker. Repo file system **is** the memory layer ([[01-doctrine#P6]]).

## Directory contract

```
.planning/harness-rewrite/
├── refs/                         # PM-curated references (read-only for workers)
│   ├── doctrine.md               # mirror of skill's codex-multi-worker-doctrine.md
│   └── friction-map.md           # PM integration of N worker outputs
├── inbox/worker-{1..N}/          # PM writes ticket JSON here
├── outbox/worker-{1..N}/         # worker writes markdown deliverable here (+ .log)
├── done/worker-{1..N}/           # PM moves consumed tickets here after review
├── pm-draft/                     # PM-authored pages (not from workers)
└── ledger.md                     # PM activity log
```

## Ticket lifecycle

1. PM writes ticket → `inbox/worker-N/<ticket_id>.json`.
2. Worker reads ticket. Single-shot; no claim file needed.
3. Worker writes deliverable → `outbox/worker-N/<ticket_id>.md` (stdout) + `.log` (stderr).
4. PM reviews → applies deletion test, citation check, vocabulary check. Move ticket to `done/worker-N/`.
5. PM appends ledger row.

No locks. Atomicity via filesystem rename (`mv` after writes finish).

## Why files, not a queue daemon

- **Doctrine P6**: filesystem = state memory. LLM sessions are stateless across resumes.
- **Progressive disclosure ([[01-doctrine#P7]])**: any newcomer can `cat ledger.md` and see what happened.
- **Reversibility**: `git diff` shows every ticket and every outbox.
- **No additional moving parts**: `mkdir`, `mv`, `ls` suffice.

## Anti-patterns observed

- **`codex-companion --background` broker** — daemon state hidden from CLI re-invocation. Use **synchronous** worker invocation redirected to a file.
- **Empty outbox file mid-flight** — until codex emits final stdout, file is 0 bytes. Check `ps aux | grep "codex exec"` for liveness.

## Ledger discipline

```markdown
| {{DATE}} HH:MM | <event> | <detail> |
```

Append-only. Every dispatch, every failure, every doctrine change leaves one row.

## Worker output gates (PM enforces)

| Gate | Test | Failure response |
|------|------|------------------|
| Fact citation | every paragraph has `path:line` | Reissue ticket, narrow `scope_files` |
| Deletion test | "deleting this paragraph would lose info" | Reissue with "remove planning prose, keep facts" |
| Vocabulary | Module/Interface/Seam/Depth/Leverage/Locality used | Reissue with explicit re-read directive |
| Word budget | within ticket `max_words` | Truncate or reissue |

## Cross-links

- [[02-supervisor-pattern]] — PM + Codex role contract
- [[01-doctrine#P6]] — file-bus principle

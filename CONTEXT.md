# auto-pilot

A Claude Code **brownfield development toolkit** (a plugin), built on an Obsidian
**vault** as its knowledge substrate. A continuous autoresearch loop keeps the
vault stocked with verified external knowledge; the autonomous multi-agent dev
loop runs on top of it, pulling the best context in and writing what it learns
back out. The discover-only Hermes learning loop is one sub-layer, not the
project's identity.

## Language

### Identity

**auto-pilot plugin**:
The repository as a whole — a Claude Code development toolkit that bundles
skills, agents, hooks, schemas, and Python helpers. The container, not a single
behaviour.
_Avoid_: the tool, the system, the app (too vague about which layer).

**auto-pilot loop**:
The flagship, single-purpose multi-agent engine inside the plugin: drives a
phased spec to merged on an EXISTING repo (brownfield). PM dispatches workers,
dual-adversarial review on frozen diffs, verify gates, atomic merge. One mode,
one mission — never confused with the plugin as a whole.
_Avoid_: the pipeline, the autopilot (collides with the plugin name), the orchestrator.

**vault**:
The Obsidian knowledge substrate the whole plugin is built on — the shared,
persistent memory the loop reads from and writes to (graphify graph + gotchas +
ADR + accumulated run learnings). The foundation, not a side tool.
_Avoid_: the wiki, the knowledge base, docs (those name outputs, not the substrate).

**vault automation**:
The pipeline that builds and maintains the vault (Obsidian + NotebookLM notebook
+ graphify graph) from a project. A first-class capability users also invoke
standalone (`/vault-build`).
_Avoid_: docs export, sync.

### Knowledge flow

**enrichment**:
Adding verified external knowledge to the vault via the autoresearch loop
(context7 library docs, web, YouTube, Reddit, dev/LLM communities, MCP). Always
passes a quality/relevance gate before it lands — unverified hits never enter.
_Avoid_: scraping, crawling, ingestion (ingestion = the gated act of recording
evidence; enrichment is its automated, autoresearch-driven form).

**injection**:
Pulling the relevant slice of the vault into a dispatch's context bundle so a
worker always reasons over the best available knowledge. The read side of the
substrate.
_Avoid_: context loading, RAG (RAG names a technique, not this seam).

**escalation**:
The hand-off from tier-1 deterministic resolution (hooks, schemas, gates, state
machines) to the tier-2 agent loop, taken only for a problem the deterministic
layer cannot resolve. May trigger a targeted enrichment before retrying.
_Avoid_: retry, fallback, the second loop (escalation is the transition, not the loop).

**mistake capture**:
Recording an error, wrong turn, or doom-loop into the vault so it is later
prevented (promoted to an enforcement asset) or fast-solved (retrieved at
dispatch). The mistake-side feed of the closed learning loop.
_Avoid_: logging, error tracking (those keep raw events; capture means a durable,
fingerprinted learning).

**brownfield**:
A target repo that already has code, tests, and conventions. The only kind of
repo the loop drives. Opposed to greenfield (new/empty), which the loop does NOT
do.
_Avoid_: existing project (too loose), legacy.

### Hermes self-improvement loop

> Vocabulary for the discover-only learning loop that mines recurring development
> friction into a durable ledger. A sub-layer of the loop, NOT the whole project.

**Run**:
One execution of the auto-pilot loop, distinguished from every other execution
by a **run identity**.
_Avoid_: session, pass, iteration.

**Run identity** (`run_id`):
The non-empty identifier that makes one Run distinct from another. Absent run
identity, a Run cannot be counted toward accumulation.
_Avoid_: session id, uuid.

**Observation**:
One sighting of a friction pattern within a single Run, before it is given a
fingerprint identity.
_Avoid_: finding (a finding is a reviewer's output, a narrower thing), hit.

**Improvement ticket**:
The durable record of one recurring friction pattern, identified by its
fingerprint, carrying a state and accumulated evidence across Runs.
_Avoid_: issue, card, item.

**Ledger**:
The durable per-project store of improvement tickets, kept outside the target
repository so it never pollutes arbitrary repos.
_Avoid_: database, store, log.

**distinct_runs**:
The count of unique Runs that have observed a pattern. The promotion gate is
defined on this — deliberately cross-Run so a single Run cannot game promotion.
_Avoid_: occurrences (that counts sightings, not Runs), frequency.

**Verdict** (`promotable` | `thin`):
The miner's gate output for a scan — whether any ticket has reached its
promotion threshold. A property of a scan, never a state of a ticket.
_Avoid_: status, result.

**Non-persisting scan**:
A miner pass that computes and emits a Verdict without writing to the Ledger.
The required behaviour when a Run has no run identity (nothing to accumulate
against, so nothing is persisted).
_Avoid_: report-only, dry-run-mode (dry-run is the flag that requests it, not
the concept).

**Source**:
The origin classification of an Observation — one of `reviewer-finding`,
`doom-loop`, `pivot`, `insight`, `wasted-tool`. Sets the promotion threshold.
_Avoid_: kind, type, category.

**Candidate asset**:
The kind of artifact that would prevent a pattern's recurrence — one of
`skill`, `hook`, `schema`, `test`, `doc`, `cache`, or none. A classification,
never a path.
_Avoid_: fix, remediation, target.

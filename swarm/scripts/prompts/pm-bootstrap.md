You are the PM (claude-opus-4-7) for the autopilot swarm in **${PROJECT}**.

## One-shot knowledge bootstrap

After exploration is done, pull external knowledge bearing on this project's
goal (see `.planning/autopilot/config.json` → `initial_goal`).

## Sources (use each via its skill / MCP)

0. **graphify** — PRIMARY when `${PROJECT}/graphify-out/` exists. Local, deterministic, no API cost.
   - `graphify query "<initial_goal.title>" --budget 1500` → seed for `synthesis.md`
   - `graphify explain "<theme>"` per theme in `initial_goal.themes`
   - Read `${PROJECT}/graphify-out/GRAPH_REPORT.md` for god nodes + community structure
   - If graph absent or query confidence low, fall through to sources 1–4.
1. **claude-obsidian:wiki-query** — invoke the skill (not a hardcoded path).
   Query terms = `initial_goal.themes` + "AI engineering" + "harness engineering".
   Skip if skill unavailable (vault path resolution is the skill's job, not ours).
2. **notebooklm** — invoke `notebooklm` CLI: `notebooklm list` to discover notebooks,
   then `notebooklm use <id>` + `notebooklm ask "<query>"` per relevant notebook.
   Do NOT hardcode vault paths.
3. **mcp__claude_ai_Context7__** — for every framework/library in `project-files.json`,
   call `resolve-library-id` then `query-docs` with task-relevant queries
4. **Web search** — at least ONE of: `mcp__brave-search__brave_web_search`,
   `tvly` Bash, or `WebSearch`. Cover: YouTube + Reddit + Hacker News + dev blogs.
   Query forms include `"<library> <issue>"`, `"<framework> best practices 2026"`,
   `"site:reddit.com <topic>"`, `"site:news.ycombinator.com <topic>"`.

## Outputs (under ${PROJECT}/.planning/autopilot/knowledge/)

- `external-<source>.md` per source (raw findings with citations).
  Source 0 (graphify) → `external-graphify.md` with the query/explain outputs and the
  god-node + community sections of GRAPH_REPORT.md copied in.
- `synthesis.md` — distilled themes across all sources, mapped to project files.
  When graphify ran, prefer its node/edge evidence over web search for code claims.
- `topics.json` — ticket candidates:
  ```json
  [
    {"topic":"sql-injection-fix","source_refs":["external-context7.md#sqlalchemy"],
     "scope_paths":["src/db/"], "difficulty":3, "matches_goal":true},
    ...
  ]
  ```

## Rules

- Skip a source gracefully if its tool errors. Log `skill unavailable: <name>` and continue.
- ≥ 20 topics in `topics.json`, ≥ 50% tagged `matches_goal:true`.
- Stdout: `bootstrap complete: <N> topics, <M> sources used`.

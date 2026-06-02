#!/usr/bin/env node
/**
 * Doc Reference Integrity — deterministic doc↔code drift guard (project-agnostic).
 *
 * Bundled by the doc-drift-audit skill as the reusable Step-5 guard. Copy into a
 * project's scripts/ dir, edit the CONFIG block for that repo, and wire into the
 * project's doc-check / CI step. No dependencies (Node built-ins only).
 *
 * Catches the MECHANICAL drift class (regex-deterministic, 100% on this class):
 *   1. inline path references in contract docs that no longer resolve
 *   2. `file:NNN` line references that point past EOF (a file that shrank)
 *   3. retired symbols described as current — with a ±N-line historical-marker
 *      window so legit "consolidated/replaced/deleted X" notes are NOT flagged
 *
 * Semantic drift (prose that lies about logic) is NOT in scope here — that needs
 * the LLM fan-out audit (the rest of the doc-drift-audit skill). Hook + skill
 * together; neither alone is enough.
 *
 * Exit 1 on any non-baselined violation; prints each with a fix hint.
 */
import fs from 'node:fs';
import path from 'node:path';

const ROOT = process.cwd();

// ─── CONFIG — EDIT PER PROJECT ───────────────────────────────────────────────
// Dirs whose .md files are "contracts" (path/symbol refs must resolve).
const CONTRACT_DIRS = ['.claude/architecture', '.claude/rules', '.claude/runbooks'];
// Standalone contract files (root + any nested interface docs).
const CONTRACT_FILES = ['CLAUDE.md', 'AGENTS.md', 'README.md'];
// Also scan every file with this basename anywhere under SOURCE_ROOTS.
const CONTRACT_FILE_BASENAME = 'CLAUDE.md';
const SOURCE_ROOTS = ['src']; // where source files + nested CLAUDE.md live
const SOURCE_EXT = /\.(ts|tsx|js|jsx|mjs|cjs)$/; // source files to scan comments in
// A token is a real path reference if it starts with one of these top-level dirs.
const PATH_PREFIX = /^(?:src|scripts|docs|\.claude|public|design-tokens|e2e|app|lib|packages)\//;
// File extensions a `name:NNN` line suffix may attach to.
const LINE_SUFFIX_EXT = /\.(ts|tsx|js|jsx|mjs|cjs|md|json|ya?ml|css|scss|py|go|rs|java|kt)$/;
// Symbols deleted from code — flagged if named as current (no nearby marker).
const RETIRED_SYMBOLS = [
  // e.g. 'fetchWithSync', 'OldServiceClass', 'deprecated_helper',
];
// Dirs whose source comments are skipped (tests, generated, vendored).
const SKIP_SOURCE = /(^|\/)(tests?|__tests__|node_modules|\.next|dist|build|generated)(\/|$)/;
const MARKER_WINDOW = 3; // lines around a retired symbol scanned for a marker
const BASELINE_FILE = 'scripts/docs/doc-reference-baseline.json'; // accepted refs
// ─────────────────────────────────────────────────────────────────────────────

// A retired-symbol mention is suppressed if a historical marker is nearby —
// i.e. the doc is recording the removal, not asserting current behavior.
const HISTORICAL_MARKER =
  /(removed|retired|legacy|former|formerly|deprecat|no longer|replaced|replaces|consolidat|merged|deleted|folded into|gone|\bwas\b|폐기|삭제|대체|구\s|이전|@deprecated)/i;

const GLOBBY = /[<>|{}*]|\.\.\.|::/;

function toPosix(p) {
  return p.split(path.sep).join('/');
}

function loadBaseline() {
  const p = path.join(ROOT, BASELINE_FILE);
  if (!fs.existsSync(p)) return new Set();
  try {
    return new Set(JSON.parse(fs.readFileSync(p, 'utf8')));
  } catch {
    return new Set();
  }
}

function walkMd(rel) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) return [];
  const stat = fs.statSync(abs);
  if (stat.isFile()) return rel.endsWith('.md') ? [toPosix(rel)] : [];
  if (!stat.isDirectory()) return [];
  return fs.readdirSync(abs, { withFileTypes: true }).flatMap((e) => walkMd(path.join(rel, e.name)));
}

function walkNamed(rel, basename, out) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) return;
  for (const e of fs.readdirSync(abs, { withFileTypes: true })) {
    if (e.name === 'node_modules' || e.name === '.next') continue;
    const child = path.join(rel, e.name);
    if (e.isDirectory()) walkNamed(child, basename, out);
    else if (e.name === basename) out.push(toPosix(child));
  }
}

function contractMarkdownFiles() {
  const set = new Set();
  for (const dir of CONTRACT_DIRS) for (const f of walkMd(dir)) set.add(f);
  for (const f of CONTRACT_FILES) if (fs.existsSync(path.join(ROOT, f))) set.add(f);
  const named = [];
  for (const r of SOURCE_ROOTS) walkNamed(r, CONTRACT_FILE_BASENAME, named);
  for (const f of named) set.add(f);
  return [...set].sort();
}

function stripFences(content) {
  return content.replace(/```[\s\S]*?```/g, '');
}

function hasMarkerNearby(lines, idx) {
  const lo = Math.max(0, idx - MARKER_WINDOW);
  const hi = Math.min(lines.length - 1, idx + MARKER_WINDOW);
  for (let j = lo; j <= hi; j += 1) if (HISTORICAL_MARKER.test(lines[j])) return true;
  return false;
}

// Split a backtick token into { refPath, suffix }. Handles every anchor style
// seen in the wild: `path`, `path:NNN`, `path:NNN-MMM`, `path:NNN,MMM,...`
// (comma lists), `path:symbol` (e.g. `main.py:create_app`). The suffix is
// everything after the first `:` that follows a known source extension; a
// non-extension `:` leaves the whole token as the path.
//
// Why this matters: the naive `/^(.+?):(\d+)(?:-(\d+))?$/` form only matched a
// single NNN or NNN-MMM and treated `file.py:33,36,37` as a literal path that
// "does not exist" — a flood of false positives in repos that cite multi-line
// anchors. This splitter resolves the path correctly AND line-checks every
// number in the suffix.
function splitRef(token) {
  const cleaned = token.replace(/[),.;]+$/g, ''); // trailing md punctuation (keep `:`)
  const m = cleaned.match(/^(.+?\.[A-Za-z0-9]+)(?::(.+))?$/);
  if (m && LINE_SUFFIX_EXT.test(m[1])) {
    return { refPath: m[1], suffix: m[2] ?? null };
  }
  // No recognized extension → a directory / extensionless path; drop any `:tail`.
  return { refPath: cleaned.replace(/:.*$/, ''), suffix: null };
}

function checkPathRefs(file, issues) {
  const content = stripFences(fs.readFileSync(path.join(ROOT, file), 'utf8'));
  for (const m of content.matchAll(/`([^`\s]+)`/g)) {
    const token = m[1];
    if (!PATH_PREFIX.test(token) || GLOBBY.test(token)) continue;
    const { refPath, suffix } = splitRef(token);
    const abs = path.join(ROOT, refPath);
    if (!fs.existsSync(abs)) {
      issues.push(`${file}: path reference does not exist: ${refPath}`);
      continue;
    }
    // Line-check only a purely-numeric suffix (NNN, NNN-MMM, NNN,MMM,…); a symbol
    // suffix like `:create_app` validates the path but cannot be line-checked.
    if (suffix && /^[\d,\s-]+$/.test(suffix) && fs.statSync(abs).isFile()) {
      const lineCount = fs.readFileSync(abs, 'utf8').split('\n').length;
      for (const nStr of suffix.match(/\d+/g) ?? []) {
        const n = Number(nStr);
        if (n > lineCount) {
          issues.push(
            `${file}: line reference past EOF: ${refPath}:${suffix} (line ${n} > ${lineCount} lines)`,
          );
        }
      }
    }
  }
}

function checkRetiredInMarkdown(file, issues) {
  if (!RETIRED_SYMBOLS.length) return;
  const lines = stripFences(fs.readFileSync(path.join(ROOT, file), 'utf8')).split('\n');
  lines.forEach((ln, i) => {
    if (hasMarkerNearby(lines, i)) return;
    for (const sym of RETIRED_SYMBOLS) {
      if (ln.includes(sym)) issues.push(`${file}:${i + 1}: retired symbol "${sym}" referenced as current`);
    }
  });
}

function* sourceFiles(rel) {
  const abs = path.join(ROOT, rel);
  if (!fs.existsSync(abs)) return;
  for (const e of fs.readdirSync(abs, { withFileTypes: true })) {
    const child = toPosix(path.join(rel, e.name));
    if (SKIP_SOURCE.test(child)) continue;
    if (e.isDirectory()) yield* sourceFiles(child);
    else if (SOURCE_EXT.test(e.name)) yield child;
  }
}

function checkRetiredInSourceComments(issues) {
  if (!RETIRED_SYMBOLS.length) return;
  const COMMENT_LINE = /(^\s*\*|\/\/|\/\*|^\s*#)/;
  for (const root of SOURCE_ROOTS) {
    for (const file of sourceFiles(root)) {
      const lines = fs.readFileSync(path.join(ROOT, file), 'utf8').split('\n');
      lines.forEach((ln, i) => {
        if (!COMMENT_LINE.test(ln) || hasMarkerNearby(lines, i)) return;
        for (const sym of RETIRED_SYMBOLS) {
          if (ln.includes(sym)) issues.push(`${file}:${i + 1}: retired symbol "${sym}" in comment as current`);
        }
      });
    }
  }
}

function run() {
  const baseline = loadBaseline();
  const issues = [];
  for (const file of contractMarkdownFiles()) {
    checkPathRefs(file, issues);
    checkRetiredInMarkdown(file, issues);
  }
  checkRetiredInSourceComments(issues);

  const unbaselined = issues.filter((i) => !baseline.has(i));
  if (unbaselined.length > 0) {
    console.error('[doc-reference-integrity] drift detected:');
    for (const i of unbaselined) console.error(`- ${i}`);
    console.error(
      `\nFix the reference, or — if intentional accepted drift — add the exact ` +
        `string to ${BASELINE_FILE}.`,
    );
    process.exit(1);
  }
  console.log(`[doc-reference-integrity] OK (${baseline.size} baselined)`);
}

run();

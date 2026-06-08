from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from _log import event


@dataclass(frozen=True)
class QuerySpec:
    name: str
    cmd: list[str]
    must_contain: list[str]
    kind: str = "pass"


@dataclass(frozen=True)
class QueryResult:
    name: str
    cmd: str
    returncode: int
    ok: bool
    missing: list[str]
    kind: str
    artifact: str


@dataclass(frozen=True)
class QuerySuiteResult:
    total: int
    passed: int
    failed: list[QueryResult]
    results: list[QueryResult]

    @property
    def ok(self) -> bool:
        return not self.failed


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    issues: list[str]
    metrics: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class CompactResult:
    removed_files: int
    preserved_files: int
    canvas_nodes: int


Runner = Callable[[list[str]], tuple[int, str, str]]
QUERY_TIMEOUT_SEC = 120


REQUIRED_VAULT_FILES = (
    "index.md",
    ".obsidian/app.json",
    "graphify/index.md",
    "graphify/_graph.json",
    "graphify/graph.canvas",
    "graphify/query-tests/summary.json",
)


CURATED_MARKDOWN = {
    "_COVERAGE_GAPS.md",
    "_GRAPH_REPORT.md",
    "_NAVIGATION.md",
    "_QUERY_TESTS.md",
    "_QUESTIONS.md",
    "_SYSTEM_MAP.md",
    "_VALIDATION.md",
}


def load_query_manifest(path: Path) -> list[QuerySpec]:
    data = json.loads(path.read_text(encoding="utf-8"))
    specs = data.get("tests", data)
    return [
        QuerySpec(
            name=str(item["name"]),
            cmd=[str(part) for part in item["cmd"]],
            must_contain=[str(part) for part in item.get("must_contain", [])],
            kind=str(item.get("kind", "pass")),
        )
        for item in specs
    ]


def default_runner(cmd: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=QUERY_TIMEOUT_SEC,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        event("graphify_query.timeout", timeout_sec=QUERY_TIMEOUT_SEC, error_type="TimeoutExpired")
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return 124, stdout, f"timeout after {QUERY_TIMEOUT_SEC}s\n{stderr}".strip()


def run_query_suite(
    specs: Sequence[QuerySpec],
    *,
    runner: Runner = default_runner,
    out_dir: Path | None = None,
) -> QuerySuiteResult:
    results: list[QueryResult] = []
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
    event("graphify_query_suite.start", total=len(specs))
    for spec in specs:
        returncode, stdout, stderr = runner(spec.cmd)
        combined = stdout + (("\nSTDERR:\n" + stderr) if stderr else "")
        missing = [marker for marker in spec.must_contain if marker not in combined]
        ok = returncode == 0 and not missing
        artifact = f"query-tests/{spec.name}.txt"
        result = QueryResult(
            name=spec.name,
            cmd=" ".join(spec.cmd),
            returncode=returncode,
            ok=ok,
            missing=missing,
            kind=spec.kind,
            artifact=artifact,
        )
        results.append(result)
        event("graphify_query_suite.result", query_name=spec.name, ok=ok, returncode=returncode)
        if out_dir:
            _write_query_artifacts(out_dir, result, combined)
    suite = QuerySuiteResult(
        total=len(results),
        passed=sum(1 for result in results if result.ok),
        failed=[result for result in results if not result.ok],
        results=results,
    )
    if out_dir:
        _write_query_summary(out_dir, suite)
    event("graphify_query_suite.done", passed=suite.passed, total=suite.total)
    return suite


def validate_graphify_vault(vault: Path) -> ValidationResult:
    vault = vault.expanduser().resolve()
    graphify = vault / "graphify"
    issues: list[str] = []
    for rel in REQUIRED_VAULT_FILES:
        if not (vault / rel).exists():
            issues.append(f"missing-required: {rel}")
    graph = _read_json(graphify / "_graph.json", issues)
    canvas = _read_json(graphify / "graph.canvas", issues)
    summary = _read_json(graphify / "query-tests" / "summary.json", issues)
    metrics = _graph_metrics(graphify, graph, summary)
    if metrics.get("community_files", 0) != metrics.get("communities", 0):
        issues.append(
            f"community-count: files={metrics.get('community_files', 0)} graph={metrics.get('communities', 0)}"
        )
    _validate_canvas(vault, graphify, canvas, issues)
    _validate_links(vault, issues)
    _validate_path_hygiene(vault, issues)
    if summary and summary.get("passed") != summary.get("total"):
        issues.append(f"query-regression: {summary.get('passed')}/{summary.get('total')}")
    return ValidationResult(ok=not issues, issues=issues, metrics=metrics)


def compact_graphify_vault(vault: Path) -> CompactResult:
    vault = vault.expanduser().resolve()
    graphify = vault / "graphify"
    community_files = sorted(graphify.glob("_COMMUNITY_*.md"))
    removed = 0
    preserved = 0
    for path in graphify.iterdir():
        if path.is_dir():
            preserved += 1
            continue
        if _is_preserved_graphify_file(path):
            preserved += 1
            continue
        if path.suffix == ".md":
            path.unlink()
            removed += 1
        else:
            preserved += 1
    _write_compact_canvas(graphify / "graph.canvas", community_files)
    _strip_unresolved_graphify_wikilinks(vault)
    return CompactResult(removed_files=removed, preserved_files=preserved, canvas_nodes=len(community_files))


def copy_query_artifacts(source_dir: Path, vault: Path) -> None:
    target = vault.expanduser().resolve() / "graphify" / "query-tests"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source_dir, target, ignore=shutil.ignore_patterns("*.txt"))


def loop_once(vault: Path, manifest: Path, *, compact: bool = False) -> ValidationResult:
    specs = load_query_manifest(manifest)
    out_dir = Path("graphify-out") / "query-tests"
    suite = run_query_suite(specs, out_dir=out_dir)
    copy_query_artifacts(out_dir, vault)
    if compact:
        compact_graphify_vault(vault)
    result = validate_graphify_vault(vault)
    if not suite.ok:
        result = ValidationResult(False, result.issues + [f"query-suite-failed: {len(suite.failed)}"], result.metrics)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("scripts/graphify_query_suite.json"))
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=1)
    args = parser.parse_args(argv)
    result = ValidationResult(False, ["not-run"])
    for _ in range(max(args.max_iterations, 1)):
        result = loop_once(args.vault, args.manifest, compact=args.compact)
        if result.ok:
            break
    print(json.dumps({"ok": result.ok, "issues": result.issues, "metrics": result.metrics}, indent=2))
    return 0 if result.ok else 1


def _write_query_artifacts(out_dir: Path, result: QueryResult, combined: str) -> None:
    stem = Path(result.artifact).stem
    (out_dir / f"{stem}.txt").write_text(combined, encoding="utf-8")
    status = "pass" if result.kind == "pass" else result.kind
    marker_lines = "- all expected markers present" if not result.missing else "\n".join(
        f"- `{marker}`" for marker in result.missing
    )
    (out_dir / f"{stem}.md").write_text(
        f"---\ntype: graphify-query-result\nproject: auto-pilot\nstatus: {status}\n---\n\n"
        f"# {stem.replace('-', ' ').title()}\n\nCommand:\n\n```bash\n{result.cmd}\n```\n\n"
        f"Expected markers:\n\n{marker_lines}\n\nResult:\n\n```text\n{combined.rstrip()}\n```\n",
        encoding="utf-8",
    )


def _write_query_summary(out_dir: Path, suite: QuerySuiteResult) -> None:
    payload = {
        "total": suite.total,
        "passed": suite.passed,
        "failed": [result.__dict__ for result in suite.failed],
        "results": [result.__dict__ for result in suite.results],
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "---",
        "type: graphify-query-suite",
        "project: auto-pilot",
        "---",
        "",
        "# Graphify query regression tests",
        "",
        f"Passed: {suite.passed}/{suite.total}",
        "",
    ]
    for result in suite.results:
        label = "PASS" if result.ok else "FAIL"
        if result.kind == "known-limitation":
            label += " (known limitation)"
        if result.kind == "expected-gap":
            label += " (expected AST-only gap)"
        stem = Path(result.artifact).stem
        lines.append(f"- {label}: [[graphify/query-tests/{stem}|{stem}]]")
    (out_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_json(path: Path, issues: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        issues.append(f"json-parse: {path}: {type(exc).__name__}: {exc}")
        return {}
    return data if isinstance(data, dict) else {}


def _graph_metrics(graphify: Path, graph: dict[str, Any], summary: dict[str, Any]) -> dict[str, int]:
    nodes = graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []
    links = graph.get("links", []) if isinstance(graph.get("links"), list) else []
    communities = {
        node.get("community")
        for node in nodes
        if isinstance(node, dict) and node.get("community") is not None
    }
    return {
        "nodes": len(nodes),
        "links": len(links),
        "communities": len(communities),
        "community_files": len(list(graphify.glob("_COMMUNITY_*.md"))),
        "query_passed": int(summary.get("passed", 0)) if summary else 0,
        "query_total": int(summary.get("total", 0)) if summary else 0,
    }


def _validate_canvas(vault: Path, graphify: Path, canvas: dict[str, Any], issues: list[str]) -> None:
    nodes = canvas.get("nodes", []) if isinstance(canvas.get("nodes"), list) else []
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "file":
            continue
        file_name = str(node.get("file", ""))
        if file_name and not (graphify / file_name).exists() and not (vault / file_name).exists():
            issues.append(f"canvas-missing-file: {file_name}")


def _validate_links(vault: Path, issues: list[str]) -> None:
    files = [path for path in vault.rglob("*") if path.is_file()]
    stems: dict[str, list[Path]] = {}
    markdown = [path for path in files if path.suffix == ".md"]
    for path in markdown:
        stems.setdefault(path.stem, []).append(path)
    for path in markdown:
        text = path.read_text(encoding="utf-8", errors="replace")
        for raw in re.findall(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", text):
            if not _wikilink_ok(vault, path, raw, stems):
                issues.append(f"broken-wikilink: {path.relative_to(vault)} -> [[{raw}]]")
        for raw in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text):
            if not _mdlink_ok(path, raw):
                issues.append(f"broken-mdlink: {path.relative_to(vault)} -> ({raw})")


def _wikilink_ok(vault: Path, source: Path, raw: str, stems: dict[str, list[Path]]) -> bool:
    target = raw.split("#", 1)[0].strip()
    if not target:
        return True
    if target.endswith((".md", ".canvas", ".html", ".json")):
        candidates = [vault / target, source.parent / target]
    else:
        candidates = [vault / f"{target}.md", vault / target, source.parent / f"{target}.md", source.parent / target]
    return any(candidate.exists() for candidate in candidates) or ("/" not in target and target in stems)


def _mdlink_ok(source: Path, raw: str) -> bool:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", raw) or raw.startswith("#"):
        return True
    target = urllib.parse.unquote(raw.split("#", 1)[0])
    return not target or (source.parent / target).exists()


def _validate_path_hygiene(vault: Path, issues: list[str]) -> None:
    for path in vault.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(vault).as_posix()
        if len(path.name) > 180:
            issues.append(f"long-filename: {len(path.name)} {rel}")
        if len(rel) > 240:
            issues.append(f"long-path: {len(rel)} {rel}")


def _is_preserved_graphify_file(path: Path) -> bool:
    if path.suffix != ".md":
        return True
    if path.name == "index.md" or path.name in CURATED_MARKDOWN:
        return True
    return path.name.startswith("_COMMUNITY_") or path.name.startswith("_MAP_")


def _strip_unresolved_graphify_wikilinks(vault: Path) -> None:
    graphify = vault / "graphify"
    markdown = [path for path in graphify.rglob("*.md") if path.is_file()]
    stems: dict[str, list[Path]] = {}
    for path in markdown:
        stems.setdefault(path.stem, []).append(path)
    for path in markdown:
        text = path.read_text(encoding="utf-8", errors="replace")

        def replace(match: re.Match[str]) -> str:
            raw = match.group(1)
            if _wikilink_ok(vault, path, raw, stems):
                return match.group(0)
            target, _, alias = raw.partition("|")
            return alias or target.split("#", 1)[0]

        updated = re.sub(r"\[\[([^\]]+)\]\]", replace, text)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def _write_compact_canvas(path: Path, community_files: Iterable[Path]) -> None:
    nodes = []
    for index, community in enumerate(community_files):
        nodes.append(
            {
                "id": f"community-{index}",
                "type": "file",
                "file": community.name,
                "x": (index % 4) * 400,
                "y": (index // 4) * 160,
                "width": 360,
                "height": 120,
            }
        )
    path.write_text(json.dumps({"nodes": nodes, "edges": []}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

---
name: quality-eval
description: >
  빅테크 13차원 코드 품질 루브릭의 SoT (single source of truth) — 차원 정의·가중치·
  hard-fail·anti-inflation·언어 자동 감지(Python/TypeScript/Go/Rust)·인프라 레이어 제외
  규칙의 출처. 데이터/레퍼런스이며 entry point 가 아님. adversarial-review-loop 가
  EVALUATE/RESCORE(codebase·multi-agent·lifecycle mode)에서 이 루브릭을 읽어 채점한다.
  점수 채점/품질 개선을 원하는 사용자 요청("코드 품질 점수", "score this project", "95점",
  "빅테크 평가", "quality loop")의 진입점은 adversarial-review-loop **codebase mode** 이다 —
  이 스킬을 직접 호출하지 말고 ARL 로 라우팅. 결과 상태는 .planning/quality/score-state.json.
---

# Quality Evaluator — 13-Dimension BigTech Rubric

모든 프로젝트에 적용 가능한 코드 품질 채점기.

## 1. Project Detection

**언어 감지** (CWD 기준):
```bash
# Python
[ -f "pyproject.toml" ] || [ -f "setup.py" ] || [ -f "requirements.txt" ]

# TypeScript/JavaScript
if [ -f "package.json" ]; then
  if [ -f "tsconfig.json" ]; then LANG=typescript; else LANG=javascript; fi
fi

# Go
[ -f "go.mod" ]

# Rust
[ -f "Cargo.toml" ]
```

**프로젝트 설정 파일** (있으면 우선 적용):
```json
// .quality-loop.json (optional)
{
  "language": "python",
  "src_patterns": ["app/**/*.py", "src/**/*.py"],
  "test_patterns": ["tests/**/*.py"],
  "exclude_patterns": ["**/infrastructure/**", "**/migrations/**", "**/generated/**"],
  "lint_cmd": "python3 -m ruff check .",
  "type_cmd": "python3 -m mypy src/ app/",
  "test_cmd": "python3 -m pytest -q",
  "coverage_threshold": 80
}
```

**자동 감지 제외 패턴** (언어별 인프라/생성 코드):
```
Python:  **/infrastructure/http/*, **/migrations/*, **/generated/*,
         **/monitoring/alerts.py, **/monitoring/metrics.py,
         **/workers/*.py (batch/daemon entry), **/__pycache__/*

TypeScript: **/node_modules/*, **/dist/*, **/build/*, **/generated/*,
            **/*.d.ts, **/prisma/generated/*, **/graphql/generated/*

Go:     **/vendor/*, **/proto/*.go, **/*_gen.go, **/mock_*.go

Rust:   **/target/*, build.rs
```

---

## 2. Validation Commands

**언어별 기본 검증 명령어:**

| 언어 | Lint | Types | Test | Coverage Gate |
|------|------|-------|------|---------------|
| Python | `python3 -m ruff check .` | `python3 -m mypy src/ app/` | `python3 -m pytest -q` | 80% |
| TypeScript | `npx eslint src/` | `npx tsc --noEmit` | `npx jest --coverage` | 80% |
| JavaScript | `npx eslint src/` | — | `npx jest --coverage` | 75% |
| Go | `golangci-lint run` | `go vet ./...` | `go test ./...` | 70% |
| Rust | `cargo clippy` | `cargo check` | `cargo test` | 70% |

`.quality-loop.json`에 `lint_cmd`/`type_cmd`/`test_cmd` 지정 시 해당 명령 사용.

---

## 3. Scoring Rubric (13 Dimensions)

> 2026-05-18 확장: Perf Budget, LLM Prompt Quality, CI/CD Quality 3 차원 추가. 기존 10 차원 weight 재배분 (총합 100).

**채점 원칙 (Strict Mode — 2026-05-18 강화):**

| Score | Meaning | Reviewer behavior |
|---|---|---|
| 95-100 | FAANG senior code review **silent approve** | "ship it" — 코멘트 없음 |
| 90-94 | FAANG approve **with nits** | 사소한 코멘트 1-3건, block 안 함 |
| 85-89 | FAANG **request changes (rework)** | 진짜 issue 발견, 머지 전 수정 요구 |
| 80-84 | FAANG **request changes (substantial)** | 다수 issue, 1-2일 작업 분량 |
| 70-79 | Mid-size 통과 / FAANG **reject** | 구조적 문제 1개 이상 |
| 60-69 | Startup 통과 / Mid-size **reject** | 주요 결함, design re-review 필요 |
| < 60 | 출시 위험 | hard block, 재설계 권장 |

**Hard-fail rules (해당 차원 max 60 강제):**
- Type Safety: `mypy --strict` 1 error 이상 → max 60
- Code Structure: ruff/format CI fail → max 60
- Test Quality: unit test red, integration collection 0, coverage < threshold → max 60
- Security: log 에 API key/token/PII 1건 노출 → max 60
- Architecture: AST boundary test red → max 60
- CI/CD: 필수 gate (lint/type/test/audit) advisory 또는 skipped → max 60
- Async Correctness: 1 missing timeout in network path → max 70

**Penalty calibration (deterministic):**
- 1 violation in dim (clear single-instance) → −5
- 2 violations same pattern → −10
- 3+ violations / pattern-wide → −15
- Hidden complexity / band-aid validator / silent-catch swallow → −10 (Codex worker 가 자주 잡는 카테고리)

**Anti-inflation guard:**
- iteration N vs N-1 차원 점수 +5 이상 상승 시 → `notes` 필드에 file:line + 변경 commit SHA 인용 의무.
- 의무 미충족 → 해당 차원 점수 N-1 값으로 강제 되돌림 + history 에 "inflation-blocked" 기록.

**Confidence rule:**
- "이게 괜찮나?" / "borderline" 라고 느끼면 항상 낮은 등급 채택.
- 85-89 vs 90-94 갈등 시 → 85-89.
- 점수는 5 단위 anchor 권장 (85/90/95). 87, 92 같은 fine-grained 는 evidence 강할 때만.

**13-dim summary (weights, canonical slug keys):**

| # | Dim slug | Weight | Hard-fail cap |
|---|----------|--------|---------------|
| 1 | `type_safety` | 9% | 60 (mypy --strict fail) |
| 2 | `test_quality` | 13% | 60 (red/no-integration/under-threshold) |
| 3 | `error_handling` | 10% | — |
| 4 | `code_structure` | 9% | 60 (ruff/format fail) |
| 5 | `configuration` | 7% | — |
| 6 | `logging` | 9% | — |
| 7 | `async_correctness` | 10% | 70 (1 missing timeout) |
| 8 | `documentation` | 7% | — |
| 9 | `security` | 7% | 60 (secret in log) |
| 10 | `architecture` | 5% | 60 (AST boundary test red) |
| 11 | `performance_budget` | 6% | — |
| 12 | `llm_prompt_quality` | 5% | — (weight=0 if no LLM calls) |
| 13 | `ci_cd_quality` | 3% | 60 (gate advisory/skipped) |

**Per-dim scoring criteria + language checkpoints:** `references/rubric-dims.md`

---

## 4. Evaluation Process

### 실행 순서

1. **Project 감지**: 언어, 소스 패턴, 테스트 패턴, 제외 패턴 결정
2. **코드 읽기**: 제외 파일을 제외한 소스 파일 분석
3. **차원별 채점**: 위 기준 + 언어별 체크포인트 적용
4. **가중 점수 계산**: `Σ(score_dim × weight_dim)`
5. **보고서 작성**: `eval-report-{iteration}.md` + `score-state.json` 저장

### 점수 결정 가이드라인

```
각 체크포인트에 대해:
  PASS  → 정상 기여
  PARTIAL → 50% 기여
  FAIL  → 0 기여, 심각도에 따라 전체 차원 점수 -5~-15

차원 점수 = 기준 점수 - Σ(위반 패널티)

판단 원칙:
  - "이게 괜찮나?" → 낮게 채점
  - 빅테크 시니어가 코드 리뷰하면 뭐라 할지 상상
  - 패턴 위반이 단 1개라도 있으면 해당 차원 -5 이상
```

---

## 5. Output Format

### score-state.json (갱신)

```json
{
  "iteration": 0,
  "timestamp": "2026-04-15T12:00:00Z",
  "project_root": "/absolute/path/to/project",
  "language": "python",
  "current_state": "ANALYZE",
  "target_score": 95,
  "mode": "sequential",
  "weighted_score": 78.9,
  "scores": {
    "type_safety":          { "score": 85, "weight": 0.09, "notes": "V4Collector uses Any in __init__" },
    "test_quality":         { "score": 72, "weight": 0.13, "notes": "No parametrize, 0 DLQ edge cases" },
    "error_handling":       { "score": 68, "weight": 0.10, "notes": "bare except at collector:206, scheduler:193" },
    "code_structure":       { "score": 82, "weight": 0.09, "notes": "_collect_league 77 lines, depth 4" },
    "configuration":        { "score": 88, "weight": 0.07, "notes": "LEAGUE_SEASON_MONTHS unvalidated" },
    "logging":              { "score": 80, "weight": 0.09, "notes": "pagination loop no event= logs" },
    "async_correctness":    { "score": 71, "weight": 0.10, "notes": "no asyncio.timeout in fetch_paginated" },
    "documentation":        { "score": 79, "weight": 0.07, "notes": "public methods missing Raises docs" },
    "security":             { "score": 84, "weight": 0.07, "notes": "error[:500] not sanitized" },
    "architecture":         { "score": 81, "weight": 0.05, "notes": "Any typed DI, no formal Protocol" },
    "performance_budget":   { "score": 70, "weight": 0.06, "notes": "no p95 latency baseline, no RSS gate" },
    "llm_prompt_quality":   { "score": 65, "weight": 0.05, "notes": "no regression fixtures, prompts inline strings" },
    "ci_cd_quality":        { "score": 78, "weight": 0.03, "notes": "no audit job, integration collection 0" }
  },
  "completed_contracts": [],
  "pending_contracts": [],
  "contract_counter": 0,
  "history": []
}
```

### eval-report-{iteration}.md

```markdown
# Quality Evaluation — {project_name} — Iteration {N}

**Date**: {ISO date}
**Language**: {python|typescript|go|rust}
**Overall Score**: {weighted}/100
**Target**: {target}/100
**Gap**: {gap}

## Dimension Scores

| Dimension | Weight | Score | Target | Gap | Grade | Top Issue |
|-----------|--------|-------|--------|-----|-------|-----------|
| Type Safety | 9% | 85 | 95 | -10 | B | Any in V4Collector |
| Test Quality | 13% | 72 | 92 | -20 | C | No parametrize |
...

**Grades**: A(90+) B(80-89) C(70-79) D(60-69) F(<60)

## Priority Improvements (by ROI)

Sorted by `gap × weight / effort_level`:
1. async_correctness: api_client.py:57 — add asyncio.timeout to fetch_paginated (+6pts, MED)
2. error_handling: collector.py:206 — narrow bare except (+4pts, LOW)
...

## BigTech / Mid-size / Startup Comparison

| Standard | Threshold | Status |
|----------|-----------|--------|
| BigTech (FAANG+) | 90+ | ❌ Not yet ({weighted}/100) |
| Mid-size | 78-89 | ✅ Meets ({weighted}/100) |
| Startup | 65-77 | ✅ Exceeds |
```

---

## 6. Standalone Use

커맨드 없이 독립 실행 시:
1. 현재 디렉토리를 프로젝트 루트로 간주
2. `.quality-loop.json` 로드 (없으면 언어 자동 감지)
3. 분석 실행
4. `.planning/quality/score-state.json` 저장
5. 요약 출력

사용 예:
- "이 프로젝트 코드 품질 점수 알려줘"
- "quality eval"
- "현재 코드 빅테크 기준으로 평가해줘"

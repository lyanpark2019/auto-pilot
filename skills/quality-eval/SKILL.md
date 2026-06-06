---
name: quality-eval
description: >
  Any codebase를 빅테크 13차원 루브릭으로 채점하는 범용 평가 스킬.
  Python/TypeScript/Go/Rust 자동 감지, 인프라 레이어 자동 제외.
  .planning/quality/score-state.json에 결과 저장.
  adversarial-review-loop codebase mode 에서 EVALUATE/RESCORE 단계에 호출됨.
  독립 호출도 가능: "코드 품질 점수 알려줘", "quality eval", "score this project"
---

# Quality Evaluator — 13-Dimension BigTech Rubric

모든 프로젝트에 적용 가능한 코드 품질 채점기.

## 1. Project Detection

**언어 감지** (CWD 기준):
```bash
# Python
[ -f "pyproject.toml" ] || [ -f "setup.py" ] || [ -f "requirements.txt" ]

# TypeScript/JavaScript
[ -f "package.json" ] && ([ -f "tsconfig.json" ] && LANG=typescript || LANG=javascript)

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

---

### Dimension 1: Type Safety (Weight: 9%)

**기준:**
| Score | 설명 |
|-------|------|
| 95-100 | 모든 public API 타입 명시, Protocol/Interface 기반 DI, 도메인 레이어에 Any/interface{} 없음 |
| 85-94 | 잘 타입화됨, 인프라 레이어에 소량의 Any |
| 75-84 | 대부분 타입화, 도메인에 일부 Any |
| 65-74 | 중요 함수 타입 누락 |
| < 65 | 광범위한 any/Any, 타입 없는 함수 다수 |

**언어별 체크포인트:**
```
Python:  - __init__ 파라미터에 Any 사용 여부
         - Protocol/ABC 기반 DI 여부 (vs 직접 클래스 의존)
         - 제네릭 타입 힌트 완성도 (list[str] vs list)
         - TYPE_CHECKING 가드 사용 여부
         - mypy --strict 통과 여부

TypeScript: - tsconfig strict: true 여부
            - any 타입 사용 횟수 (0 = 100, 1-5 = 90, 6-20 = 75)
            - unknown vs any 사용 패턴
            - 제네릭 활용도

Go:      - interface{}/any 사용 횟수
         - 명시적 interface 정의 여부
         - 타입 assertion 남용 여부

Rust:    - unwrap() 남용 여부 (Result/Option 처리)
         - lifetime 명시 완성도
```

---

### Dimension 2: Test Quality (Weight: 13%)

**기준:**
| Score | 설명 |
|-------|------|
| 90-100 | 파라미터화 테스트, 경계값 케이스, 오류 경로, 높은 커버리지 |
| 80-89 | 좋은 커버리지, 일부 파라미터화 |
| 70-79 | 대부분 해피패스, 파라미터화 없음 |
| 60-69 | 핵심 엣지 케이스 미테스트 |
| < 60 | 테스트 부실 또는 없음 |

**언어별 체크포인트:**
```
Python:  - @pytest.mark.parametrize 사용 여부
         - DLQ/재시도/페이지네이션 경계 테스트
         - fixture 격리 (공유 가변 상태 없음)
         - 커버리지 80%+ (제외 파일 빼고)
         - AsyncMock 올바른 사용

TypeScript: - describe/it 계층 구조
            - jest.each 파라미터화
            - 에러 경로 테스트 (rejects, throws)
            - 커버리지 80%+

Go:      - table-driven tests 패턴
         - 서브테스트 (t.Run)
         - 에러 케이스 커버

Rust:    - #[cfg(test)] 모듈
         - assert!/assert_eq! 품질
         - proptest/quickcheck 사용 여부
```

---

### Dimension 3: Error Handling (Weight: 10%)

**기준:**
| Score | 설명 |
|-------|------|
| 90-100 | 모든 예외 타입 명시, event= 로그, 예외 삼킴 없음 |
| 80-89 | 대부분 명시, 소량 누락 |
| 68-79 | bare except/catch 여러 곳, event= 로그 일부 누락 |
| < 68 | 광범위한 bare catch, 예외 삼킴 |

**언어별 체크포인트:**
```
Python:  - except Exception 없음 (명시적 타입)
         - asyncio.CancelledError를 catch하지 않음
         - 에러 로그에 event= prefix + error_type= 필드
         - raise ... from e 체이닝

TypeScript: - catch (e) { } 빈 블록 없음
            - Error 서브클래스 사용
            - Promise rejection 처리

Go:      - errors.Is/As 사용
         - 에러 래핑 (fmt.Errorf("%w", err))
         - 에러 반환 무시 없음 (_, _ = )

공통:    - 에러 로그에 구조화 필드 (file, function, context)
         - 오류 복구 불가능 시 panic/exit vs 로그+계속 전략
```

---

### Dimension 4: Code Structure (Weight: 9%)

**기준:**
| Score | 설명 |
|-------|------|
| 90-100 | 함수 < 40줄, 중첩 3단계 이하, SRP 준수 |
| 82-89 | 소수 위반, 하나의 복잡한 함수 |
| 70-81 | 1-2개 추출 필요한 함수 |
| < 70 | 다수 과도하게 복잡한 함수 |

**체크포인트:**
```
- 파일당 줄수 300 이하 (자동 생성 제외)
- 함수/메서드 40줄 이하
- 중첩 깊이 3단계 이하 (for → try → if → if = 4단계 위반)
- 클래스/함수 이름이 단일 책임 반영
- early return 패턴 사용 (중첩 감소)
```

---

### Dimension 5: Configuration (Weight: 7%)

**기준:**
| Score | 설명 |
|-------|------|
| 95-100 | 모든 임계값 설정 파일 관리, 로드 시 검증, enum 가드 |
| 88-94 | 잘 관리됨, 소량 누락 |
| 80-87 | 대부분 관리됨, 일부 매직 넘버 |
| < 80 | 광범위한 하드코딩 |

**체크포인트:**
```
Python:  - pydantic Settings/Field 사용
         - ge/le/gt/lt 제약 명시
         - @field_validator, @model_validator 활용
         - 환경변수 validation_alias 명명

TypeScript: - zod/yup 스키마 검증
            - process.env 직접 접근 없음 (설정 레이어 통해서)

공통:    - 매직 넘버 없음 (상수 또는 설정으로)
         - 누락 설정 시 명확한 에러 메시지
         - 개발/스테이징/프로덕션 환경 분리
```

---

### Dimension 6: Logging/Observability (Weight: 9%)

**기준:**
| Score | 설명 |
|-------|------|
| 90-100 | 모든 주요 작업에 event= 로그, 구조화 필드 |
| 80-89 | 대부분 구조화, 소량 누락 |
| 75-79 | 루프/페이지네이션 내부 로그 누락 |
| < 75 | 비구조화 로그 다수 |

**체크포인트:**
```
공통:   - 주요 작업마다 event= prefix (또는 구조화 로그 필드)
        - 에러 로그에 error_type=, error= 필드
        - 성공/실패 경로 모두 로그
        - 성능 임계값 초과 시 경고

Python: - logger.info("event=X key=val") 패턴 일관성
        - 외부 API 호출 전후 로그 (latency 포함)

TypeScript: - structured logging (winston/pino)
            - correlation ID 전파
```

---

### Dimension 7: Async Correctness (Weight: 10%)

**기준:**
| Score | 설명 |
|-------|------|
| 90-100 | 모든 네트워크 호출에 타임아웃, blocking I/O 없음 |
| 80-89 | 대부분 올바름, 하나의 누락 타임아웃 |
| 71-79 | 페이지네이션/루프에 타임아웃 없음, 잠재적 blocking I/O |
| < 71 | 다수의 async 문제 |

**언어별 체크포인트:**
```
Python:  - asyncio.timeout() 또는 aiohttp timeout 파라미터 설정
         - async 컨텍스트에서 blocking I/O (파일 읽기, time.sleep) 없음
         - asyncio.CancelledError 올바른 처리
         - asyncio.gather 에러 처리 패턴
         - Semaphore 과부하 방지

TypeScript: - Promise timeout 래핑
            - async/await 올바른 에러 처리
            - unhandled rejection 없음

Go:      - context.WithTimeout 사용
         - goroutine leak 없음 (defer cancel())
         - channel 데드락 없음
```

---

### Dimension 8: Documentation (Weight: 7%)

**기준:**
| Score | 설명 |
|-------|------|
| 88-100 | 모든 public API docstring (Args/Returns/Raises) |
| 79-87 | 대부분 문서화, 소량 누락 |
| 70-78 | 부분적 docstring |
| < 70 | 핵심 문서 누락 |

**체크포인트:**
```
공통:   - public 함수/클래스에 docstring/JSDoc/GoDoc
        - 비자명 로직에 인라인 주석
        - CLAUDE.md/README 현행화 (코드와 불일치 없음)
        - Args/Returns/Raises (또는 @param/@returns)

Python: - 복잡한 로직에 # 설명
        - 예외 동작 문서화 ("예외 없이 빈 list 반환" 등)
```

---

### Dimension 9: Security (Weight: 7%)

**기준:**
| Score | 설명 |
|-------|------|
| 92-100 | API 키 redact, 에러 메시지 sanitize, 입력 검증 |
| 84-91 | 키 redact됨, 소량 검증 누락 |
| 75-83 | redact 있으나 검증 갭 |
| < 75 | 비밀 정보 로그 노출 또는 검증 없음 |

**체크포인트:**
```
공통:   - 로그에 API 키/토큰 노출 없음
        - 에러 메시지에 시크릿 포함 안 됨 (DLQ 저장 포함)
        - 외부 API 응답 파싱 전 입력 검증
        - SQL injection 위험 없음 (파라미터화 쿼리)
        - 의존성 취약점 (안전한 버전 사용)

Python: - secrets 라이브러리 사용 (random 대신)
        - os.path.join 사용 (path traversal 방지)
```

---

### Dimension 10: Architecture (Weight: 5%)

**기준:**
| Score | 설명 |
|-------|------|
| 92-100 | Protocol/Interface 경계, 단방향 의존, 원형 의존 없음 |
| 81-91 | 좋은 DI, 소량 결합 |
| 70-80 | 일부 타이트 결합, Protocol 경계 없음 |
| < 70 | 아키텍처 문제 |

**체크포인트:**
```
공통:   - 레이어 경계 준수 (domain → infra 역방향 없음)
        - Protocol/Interface 기반 외부 의존성 주입
        - 원형 import 없음
        - 단일 책임 클래스 (변경 이유 1개)

Python: - domain 레이어에서 infrastructure import 없음
        - bootstrap.py 또는 명확한 DI 진입점
        - 프로세서/전략 패턴 확장성
```

---

### Dimension 11: Performance Budget (Weight: 6%)

**기준:**
| Score | 설명 |
|-------|------|
| 92-100 | latency/메모리/throughput SLO 명시 + CI gate, regression alarm |
| 80-91 | 일부 SLO 정의됨, 일부 측정 누락 |
| 70-79 | 측정만 있고 게이트 없음 |
| < 70 | perf 측정/budget 부재 |

**체크포인트:**
```
공통:   - p50/p95/p99 latency 측정 + CI baseline
        - 메모리 ceiling (RSS) 게이트
        - DB/외부 호출 N+1 방지 (eager load/batch)
        - 콜드 스타트 / 부팅 시간 측정

Python: - pytest-benchmark baseline + --benchmark-compare-fail
        - psutil RSS 측정 + 임계값 assert
        - asyncio 동시성 한계 측정 (Semaphore tuning)

TypeScript: - lighthouse CI, web-vitals 게이트
            - bundle size budget
            - LCP/CLS/INP 측정

Go/Rust: - pprof 프로파일 baseline, benchmark suite
```

---

### Dimension 12: LLM Prompt Quality (Weight: 5%)

> LLM 호출이 없는 프로젝트는 weight=0 으로 두고 다른 차원에 비례 재배분.

**기준:**
| Score | 설명 |
|-------|------|
| 90-100 | prompt 버전 관리 + regression suite + structured output schema + drift alarm |
| 80-89 | regression baseline 있음, prompt schema 일부 |
| 70-79 | prompt 하드코딩, 출력 검증만 |
| < 70 | prompt 자유 텍스트, regression 없음 |

**체크포인트:**
```
공통:   - prompt 파일 분리 (.md / yaml), 인라인 string 금지
        - structured output schema (JSON Schema / pydantic / zod)
        - regression fixture (N=20+ synthetic + adversarial)
        - 모델 업그레이드 시 diff gate (max-call cap, budget cap)
        - 출력 시 PII/secret 누출 차단 sanitizer

Python: - pydantic Response model, instructor / openai responses.parse
        - prompt template lint (placeholder 미바인딩 검출)

TypeScript: - zod 스키마, ai-sdk generateObject / streamObject

도메인:  - intent classifier 정확도 baseline (true label vs predicted)
        - hallucination 차단 (tool/function calling, JSON mode)
```

---

### Dimension 13: CI/CD Quality (Weight: 3%)

**기준:**
| Score | 설명 |
|-------|------|
| 90-100 | 모든 gate (lint/type/test/coverage/integration/perf/audit) 강제 + 빠른 피드백 (<5분) |
| 80-89 | 핵심 gate 강제, 일부 advisory |
| 70-79 | gate 일부 누락 또는 5-10분 |
| < 70 | gate 부재 또는 너무 느림 (>10분) / advisory only |

**체크포인트:**
```
공통:   - PR 머지 전 모든 gate 통과 강제 (branch protection)
        - lint / type / unit test / integration collection ≥1
        - coverage 임계값 (언어별 70-80%) CI fail
        - 의존성 audit (npm/pip-audit/cargo audit)
        - SBOM 생성 (CycloneDX, SPDX)
        - 비밀/PII 누출 grep gate
        - 워크플로우 YAML/스크립트 parse gate
        - 빌드+테스트 < 5분 (slow gate = skipped gate)

Python: - mypy --strict, ruff check + format
        - pytest -m "not integration" 와 -m integration 분리, 둘 다 실행
        - --cov-fail-under

TypeScript: - tsc --noEmit, eslint, biome / prettier --check
            - vitest / jest --coverage
```

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

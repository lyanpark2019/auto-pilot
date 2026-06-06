<!-- Single source for detailed per-dimension scoring guidance.
     Summary table + weights live inline in SKILL.md § 3.
     This file is read by Claude eval Agent (Track A) and Codex eval (Track B) during EVALUATE/RESCORE.
     Do NOT duplicate the weight column here — SKILL.md §3 is the weight SoT. -->

# Rubric Dimensions — Detailed Scoring Guidance

Per-dim criteria + language-specific checkpoints. Used by evaluators during EVALUATE/RESCORE steps.

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

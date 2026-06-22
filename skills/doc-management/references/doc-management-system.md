# Graphify-Native 문서 관리 시스템 — 스펙 v1 (2026-06-06)

> 모든 프로젝트에 적용 가능한 문서 **생성 → 관리 → 업데이트 자동화** 체계. PickL-API 에서 end-to-end 1회 검증 (22937→code-only 그래프, 345p 손-유지 wiki 폐기, design 10 + rules 4 재작성, 이중 적대 리뷰 r1 REJECT→r2 APPROVE, 가드+훅 잠금).
> 스킬 본체: 이 플러그인의 `doc-management` 스킬 (`../SKILL.md`, 3-mode: REBUILD/MAINTAIN/AUDIT; REBUILD 실행 절차 = `rebuild-phases.md`) — 이 문서는 시스템 설계 스펙 (왜 이 구조인가 + 계약 + 자동화 사양). (구 `graphify-doc-rebuild` 스킬은 doc-management 로 통합되어 retire.)

---

## 0. 해결하는 문제

손-유지 구조 문서(per-module wiki, "what-calls-what" 페이지)는 **반드시 썩는다** — 코드와 일치를 강제하는 메커니즘이 없기 때문. 증거: PickL 345-page llm-wiki (생성 직후부터 drift, 결국 전량 폐기). LLM 으로 재생성해도 미검토 prose 는 rot 을 재생산할 뿐.

해법 = **층 분리**: 썩을 수 있는 것(구조 서술)은 기계 생성으로, 썩지 않는 것(결정/의도)만 손으로, 그 사이(repo docs)는 생성+리뷰 게이트로.

## 1. 3층 모델 (시스템의 뼈대)

| 층 | SoT | 작성 주체 | drift 방어 |
|---|---|---|---|
| **What** — 모듈/호출/의존 구조 | 코드 그래프 (graphify Tree-sitter AST, **code-only 필터**) | 기계. 소비는 `graphify query/explain/path` **질의** | 코드에서 재생성 → drift 구조적 불가. post-commit hook 자동 갱신 |
| **Why** — 결정·사고·gotcha·governance | `intent/` 층 (ADR + gotcha + history + governance) | 사람/에이전트 — **충실-추출만**: 모든 entry 출처 인용, 날조 금지, 모르면 `(why not documented)` | 본질적으로 historical → 안 썩음. 옛 문서 삭제 **전** harvest ("none lost" 불변식) |
| **Generated mirror** — repo `.claude/design/`·rules·nav·docs | 위 2층에서 생성, `file:line`/심볼앵커 인용 | 에이전트 작성 → **이중 적대 리뷰 통과 시만 진입** | L2 가드(기계) + SHA freshness(자동 탐지) + AUDIT(의미) |

**금지 패턴**: per-module 구조 페이지 (rot machine) · 구조 facts hand-mirror (그래프 질의로 대체) · governance 재진술 (단일 SoT 페이지 + 한 줄 인용만) · 미검토 LLM prose 직행.

## 2. 표준 레이아웃 (프로젝트 적용 시)

```
<repo>/
  graphify-out/            # What 층 (생성물, post-commit hook 자동 갱신)
  .claude/
    design/                # 서브시스템 topic 문서 ~8-10 (per-module 금지)
    rules/                 # 하드룰 + governance 단일 SoT 페이지
    architecture/          # 슬림 stub — cross-cutting 규칙만 (구조 상세 = 그래프)
    _archive/              # 미검증 구문서 격리
  docs/
    README.md              # 인덱스 (게이트 강제)
    OVERVIEW.md            # 사람용 추상 진입
    _archive/              # 〃
  CLAUDE.md                # nav 포인터 (≤50줄)
<vault>/projects/<repo>/   # 작업장→미러: _graph/ + intent/ (re-export 대상, 손-병행유지 금지)
```

Why 층 위치는 프로젝트 선택: vault `intent/`(PickL 방식) 또는 repo `docs/adr/`+`.claude/intent/`.

## 3. 생성 (REBUILD — 신규/전면 재구축)

`rebuild-phases.md` 7-phase 가 실행 사양. 요지:

0. **진단 게이트** — rot 은 가설이지 사실 아님. 병렬 read-only 감사 (모순 스캔/구조 건강/git-lag) → `disciplined` 면 부분 정리로 끝, `patchwork` 만 전면 재구축.
1. **code-only 그래프**: `graphify update . --force`(AST-only, 키 불필요, 삭제 후 graph shrink 허용) → graph.json 필터: `file_type=="code"` **AND** 언어 확장자 AND tests/scratch 경로 제외 (file_type 단독 불충분 — json/sh/test 도 달림) → canonical 레이아웃 (`<dir>/graphify-out/graph.json`) → `cluster-only` → **도메인 질의로 필터 검증** (fixture 가 나오면 실패).
2. **vault workbench**: `_graph/` + `intent/` harvest (출처 인용 강제).
3. **그래프-기반 authoring**: 서브시스템당 에이전트 1 — 질의 → **실소스 정독** (이 단계가 stale fact 를 잡음) → `file:line` 인용 + Why 직조.
4. **repo 재작성** + 클린-슬레이트 옵션: 재작성+리뷰 통과분만 live, **나머지 전부 `_archive/`** (= 추후 검증-추출 소스). root 문서(README/CLAUDE.md/AGENTS.md/OVERVIEW/docs-index)도 새 구조 기준 fresh. 예외 2종만 live 잔류: GENERATED (OpenAPI export 류) + **machine-read docs** (게이트 스크립트가 파싱하는 문서 — 탐색: `rg -l 'docs/.*\.md' <scripts> --type py`; PickL 선례 `check_module_size.py:26` → `modularization.md`). ops-필수 문서는 **같은 세션/커밋에서** 검증 후 기존 경로 fresh 복원 (frontmatter `verified:` + `source_commit`) — 공백기 금지.
5. **이중 적대 리뷰 (비선택, 자가서비스 불가)**: Codex-adversarial + cold Claude 병렬, 인용 파일 전부 열어 반박. 둘 다 APPROVE + 신규 finding 0 까지. (author 는 자기 P0 구조적으로 못 봄 — r1 REJECT 가 정상.)
6. **anti-re-rot 잠금** — §5.
7. **ship**: 로컬 게이트 EXIT 0 → docs 브랜치 → **deploy boundary 확인** (CI 에 path filter 없으면 docs-only 머지가 prod 재배포 — 코드 PR 번들) → vault 미러 강등 → 핸드오프 메모리.

## 4. 관리 (거버넌스 계약)

- **frontmatter 계약** (모든 generated-mirror 문서): `type` · `topic` · `source_commit`(작성 시점 HEAD) · `manual_edit`(true 면 자동화가 안 건드림). 검증-복원 문서는 `verified: <date>` 추가.
- **인용 규칙**: `app/path.py:NNN` 또는 `` `file.py` → `SYMBOL` `` 심볼앵커. churn 파일은 **앵커 강제** (line 번호는 즉시 rot). `.md:NN` 교차 인용 금지 — 섹션명 인용.
- **단일 SoT**: 한 fact 는 한 페이지가 출처, 나머지는 한 줄 인용. governance(머지/배포/승인)는 페이지 1개.
- **아카이브 정책**: `_archive/` = frozen·reference-only·게이트 exempt. "현재 진실" 아님. 필요 시 검증 에이전트가 추출해 live 로 — **검증 없이 복사 금지**.
- **레지스트리 룰** (도구 재난립 방지): 새 doc 도구/스킬 만들기 전 기존 확인, 대체 생성이면 같은 변경에서 전임자 retire.

## 5. 업데이트 자동화 (MAINTAIN — 코드 변경 후 문서 추적)

| 레이어 | 대상 drift | 메커니즘 | 트리거 | 차단? |
|---|---|---|---|---|
| L1 generate | 사실 (엔드포인트/스키마) | OpenAPI 류 export + `--check` freshness | 게이트 | **차단** |
| L2 deterministic | dead path · `:NNN`>EOF · 죽은 심볼 · retired token 부활 | doc→source ref 가드 (`check-doc-reference-integrity.mjs` 패턴: 경로 resolve + EOF + 심볼앵커 resolve + `RETIRED_SYMBOLS` denylist + `_archive` exempt + 삭제-구문("removed in") historical 허용; CI 병행 `scripts/docs/check_doc_reference_integrity.py`) | 게이트 (CI) | **차단** |
| 그래프 갱신 | 구조 lag | `graphify hook install` — post-commit 자동 재빌드 | 커밋마다 | 자동 |
| **L3 SHA freshness** | design 문서 stale (인용 소스가 변경됨) | `check_design_doc_freshness.py` (~60줄, LLM 0): 문서별 frontmatter `source_commit` 파싱 → 본문 cited 소스 경로 수집 (L2 가드의 경로 regex 재사용) → `git diff --name-only <source_commit>..HEAD -- <paths>` 교집합 ≠ ∅ → **STALE 보고** (문서 + 바뀐 파일 목록). frontmatter 계약 검사 동봉 | 게이트 **STALE 차단 (exit 1)** + post-commit 한 줄 | **STALE 차단** (exit 1). frontmatter-contract gap 은 WARN advisory (exit 0 유지). 한계 명시: rename/move 미추적(경로 기준) |
| MAINTAIN 실행 | STALE 해소 | freshness 출력 소비 → 문서별 refresh 에이전트: 그래프 재질의 → 소스 재독 → 인용/prose 갱신 → `source_commit` bump → 대규모면 이중리뷰 | on-demand 배치 (탐지=자동, 갱신=리뷰 동반) | — |
| AUDIT 주기 | semantic (prose↔로직 불일치 — 기계가 못 잡음) | read-only 병렬 fan-out · evidence 서열 **code>tests>CLI>config>generated>logs** · stale-as-current(고침) vs correct-historical(둠) 구분 · P0/P1/P2 → fix 는 MAINTAIN 위임 | 주기/대형 리팩토링 후 | 보고 |

**금지**: 전자동 LLM 재작성 + 자동커밋 (미검토 prose = rot 재생산). 탐지는 자동, 갱신은 리뷰 동반.
**비채택**: claim-ledger (수동 JSON + 수동 `last_verified` bump) — 그 자체가 hand-maintained rot 패턴. SHA freshness + AUDIT 가 대체.

## 6. 새 프로젝트 적용 절차

1. per-repo discovery (`rebuild-phases.md` 표): `<LOCAL_GATE>` · `<REF_GUARD>`(없으면 생성+게이트 wire) · `<DEPLOY_GOVERNANCE>` · `<MEMORY_DIR>` · `<MACHINE_READ_DOCS>`.
2. Phase 0 진단 → 판정에 따라 전면 REBUILD 또는 부분 정리.
3. REBUILD 시 §3, 이후 §4 계약 + §5 자동화 설치 (가드 wire + graphify hook + freshness 스크립트).
4. 이후 일상: 코드 변경 → hook 이 그래프 갱신 → freshness WARN → MAINTAIN 배치 → 주기 AUDIT.

## 7. 하드원 gotcha (전부 실사고)

| gotcha | 대응 |
|---|---|
| graphify full corpus 가 `.md` ingest → **stale 문서가 그래프로 역류** | What 층은 항상 code-only 필터 |
| `file_type=="code"` 단독 불충분 | + 확장자 + tests/scratch 경로 제외 |
| graph.json edge 키 = `links` (networkx) | 양쪽 키 처리 |
| `cluster-only` 는 `<dir>/graphify-out/graph.json` 레이아웃 요구 | canonical 레이아웃으로 기록 |
| full semantic 빌드는 별도 | `graphify extract . --mode deep` |
| code graph 갱신 | `graphify update . --force` = AST-only + 삭제 후 graph shrink 허용 |
| vault-상대 인용(`intent/...`)·`[[wikilink]]` 는 repo 포팅 시 dangle | repo-상대 경로 + 표준 링크로 변환 |
| 줄번호 인용은 구조변경 즉시 rot | 심볼앵커/섹션명 인용 |
| Why 는 그래프에 없음 | 삭제 전 harvest |
| machine-read doc 이동 = 게이트 파손 | `<MACHINE_READ_DOCS>` 탐색 후 live 예외 |
| docs-only 머지 = no-path-filter CI 에서 prod 재배포 | 코드 PR 번들 |
| author 자기 P0 자가탐지 불가 | 이중 적대 리뷰 비선택 |
| ops 문서 아카이브 공백기 | verify-restore 같은 커밋 |

## 8. 검증 체크리스트 (시스템 가동 판정)

- [ ] code-only 그래프 질의가 도메인 클래스 반환 (fixture 아님)
- [ ] intent 전 entry 출처 인용, 날조 0
- [ ] governance 단일 SoT + 재진술 0
- [ ] per-module 구조 wiki 0개, dangling-ref 스윕 0건
- [ ] 이중리뷰 양측 APPROVE (신규 finding 0)
- [ ] L2 가드 DOC_ROOTS = 새 트리, 게이트 wire, EXIT 0
- [ ] `graphify hook status` = installed
- [ ] freshness 스크립트 게이트 STALE-blocking wire (exit 1) + frontmatter 계약 WARN advisory + 전 문서 통과
- [ ] vault = 미러 강등 명시
- [ ] 자체평가에 "100/100"/"완벽"/"최종" 없음 — 잔여 리스크 명시

## 9. 알려진 한계 (정직)

- 기계 가드 사각: `.md→.md` 인용 · range 상한 · valid-but-wrong-line — 심볼앵커 관례 + 리뷰로 완화, 차단 불가.
- freshness v1 rename 미추적 (git --follow 비용).
- semantic drift 는 AUDIT 주기 사이 창에서 존재 가능.
- `_archive/` 추출-모델: 해당 영역 작업 시점에 검증 비용 발생 (선불 아님).

## 10. 센티넬 컨벤션 + incremental refresh 체계 (v2)

### 센티넬 마커 (sentinel convention)

생성된 docs 와 사람이 수정하는 구역을 같은 파일에 공존시키는 규칙:

```
<!-- @generated -->
...기계가 소유하는 구역 (MAINTAIN 이 덮어씀)...
<!-- /@generated -->

<!-- @user -->
...사람이 소유하는 구역 (절대 덮어쓰지 않음)...
<!-- /@user -->
```

- `<!-- @generated -->` 구역: graphify 질의 + 소스 re-read 로 교체. 리뷰 필요.
- `<!-- @user -->` 구역: `sentinel_merge.py` 가 byte-identical 보존. 자동화가 절대 건드리지 않음.
- 마커 없는 기존 문서: `sentinel_merge` 가 전체 overwrite + stderr warn 출력 (기존 동작 유지).

### frontmatter bootstrap

`scripts/bootstrap_frontmatter.py` — 4개 필수 키가 없는 docs 를 자동 주입:

| 키 | 추론 방법 |
|---|---|
| `type` | path 세그먼트 (`architecture/`→architecture, `modules/`→module, `operations/`→operations, 기타→doc) |
| `topic` | 파일명 stem (숫자/대시 접두사 제거) |
| `source_commit` | `git rev-parse HEAD` |
| `manual_edit` | `false` (기본) |

기존 키 보존 (부분적으로 있는 frontmatter = merge). `--write` 없으면 dry-run. 멱등.

**주의 (false-fresh 위험):** `source_commit=HEAD` 스탬프는 "이 문서는 HEAD 기준으로 정확하다"고 L3 freshness 게이트에 단언한다. 검증하지 않은/stale 문서에 bootstrap 을 실행하면 실제 drift 가 next 코드 변경 시까지 무음으로 숨겨진다. **bootstrap 은 AUDIT 패스 완료 후(또는 방금 직접 검증한 문서에만) 실행할 것 — 미감사 docs 의 post-audit 기준선 설정 도구이지, 검증 도구가 아니다.**

### affected-docs impact selection

`scripts/affected_docs.py` — 변경된 소스 파일에서 docs refresh 영향 셋을 확장:

1. 변경 파일별로 `graphify affected <symbol>` 실행 (없으면 basename fallback).
2. DOC_ROOT 전체를 grep — 영향받은 심볼/경로를 인용하는 docs 수집.
3. 중복 제거 후 정렬 출력 → MAINTAIN 의 "refresh 대상 셋" 으로 소비.

직접 STALE 인 docs 외에 sibling/dependent docs 까지 자동 확장.

### local hook trigger model

`scripts/install_doc_hooks.sh` — 현재 repo 의 `.git/hooks/` 에만 설치 (global 설치 없음):

| hook | 동작 | 차단? |
|---|---|---|
| `post-commit` | `graphify update` (advisory) + freshness print | 아니오 |
| `pre-push` | freshness check — STALE 이면 exit 1 | **예** |

멱등 (marker 가 이미 있으면 append 안 함). CI hook 은 선택사항 — 로컬 게이트가 기본.

### vault sentinel-aware sync

`~/.claude/scripts/vault-sync.sh` (global deploy hook) 의 curated docs mirror 가
`sentinel_merge.py` 를 통해 per-doc 쓰기를 수행:

- vault 에 이미 docs 가 있으면 `<!-- @user -->` 구역 보존.
- vault doc 미존재 시 그냥 write.
- `sentinel_merge` 실패 시 plain copy fallback — deploy 절대 중단 않음.

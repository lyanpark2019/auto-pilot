***

description: 하네스 엔지니어링 방식 CLAUDE.md 체계 구축 (금지 사항 중심)
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent
---------------------------------------------------------

프로젝트에 하네스 엔지니어링 방식의 CLAUDE.md 체계를 구축한다.

## 원칙

Claude는 세션 시작 시 CLAUDE.md를 컨텍스트로 로딩한다 (공식 docs: "concise and specific instructions is the most effective way"). **코드만 봐서 모르는 프로젝트 특화 금지 사항**만 적는다. "잘하는 법"이 아니라 "하지 말아야 할 것 + 왜"를 적는다.

### CLAUDE.md 로딩 규칙 (Claude Code 공식)

* `./CLAUDE.md` 또는 `./.claude/CLAUDE.md` — 프로젝트 루트, 매 세션 로딩
* `app/services/CLAUDE.md` — 해당 디렉토리 파일 작업 시 자동 로딩
* `~/.claude/CLAUDE.md` — 글로벌 개인 설정, 모든 프로젝트에 적용

## 실행

### 1. 분석

```Shell
# 구조
find . -type d -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/__pycache__/*' -not -path '*/.venv/*' -maxdepth 3 | sort

# 사고 이력 (금지 사항 소스)
git log --oneline --grep="fix\|revert\|hotfix\|bug" | head -20

# 기존 CLAUDE.md
find . -name "CLAUDE.md" -not -path "./.claude/*" | sort

# 대형 파일 (300줄 초과 후보)
find . -name '*.py' -o -name '*.ts' -o -name '*.tsx' | xargs wc -l 2>/dev/null | sort -rn | head -10
```

### 2. 루트 CLAUDE.md 작성 (50줄 이내)

```Markdown
# CLAUDE.md

{프로젝트 한 줄 설명}

## Commands
` ` `bash
{빌드/테스트/린트 — 3줄 이내}
` ` `

## 절대 금지
| 금지 | 이유 (사고 레퍼런스) |
|------|---------------------|
| {금지 사항} | {실제 장애/버그/PR 번호} |

## 폴더별 상세
| 폴더 | 내용 |
|------|------|
| [`{path}/CLAUDE.md`]({path}/CLAUDE.md) | {한 줄} |

## 상세 문서
| 문서 | 내용 |
|------|------|
| [`docs/{path}`](docs/{path}) | {한 줄} |
```

### 3. 폴더별 CLAUDE.md (10줄 이내, 금지만)

대상 선정 기준 (우선순위):

1. **사고 발생 폴더** — git log에서 fix/revert가 집중된 디렉토리
2. **레이어 경계** — DB/service/API 등 역할이 다른 폴더
3. **소스 10개 이상** — 규칙 없으면 일관성 깨짐

```Markdown
# {레이어명} — 금지 사항

- **{금지}** — {이유}
- **{금지}** — {이유}
```

### 4. 검증

```Shell
# 줄 수 확인 (루트 50줄, 폴더별 10줄 목표)
find . -name "CLAUDE.md" -not -path "./.claude/*" -exec sh -c 'echo "$(wc -l < "$1") $1"' _ {} \;

# 금지 사항 테이블 존재 확인
grep -l "금지\|NEVER\|禁止\|Don.t" $(find . -name "CLAUDE.md" -not -path "./.claude/*")
```

## 금지 사항 발굴법

| 소스            | 명령/방법                                            |
| ------------- | ------------------------------------------------ |
| revert/hotfix | `git log --oneline --grep="fix\|revert\|hotfix"` |
| Sentry 반복     | 같은 에러 2회+ → 패턴화                                  |
| 코드 리뷰 빈출      | PR comment에서 반복 지적                               |
| SDK/인프라 제약    | 문서에 없는 런타임 동작 (예: Supabase SDK auth state 오염)    |
| 묵시적 규칙        | 시간대, 키 네이밍, 컬럼 규칙 등 코드로 읽히지 않는 것                 |

**이유 없는 금지는 무시된다.** 반드시 사고 레퍼런스 또는 구체적 이유 포함.

## 하지 말 것

* 일반 best practice (SOLID 설명, "깔끔한 코드" 등 — Claude가 이미 앎)
* 코드에서 바로 읽히는 것 (함수 시그니처, import 경로)
* 루트 CLAUDE.md 50줄 초과
* TODO/미래 계획 (이슈 트래커 사용)
* 장황한 아키텍처 설명 (`docs/architecture/`로 분리)


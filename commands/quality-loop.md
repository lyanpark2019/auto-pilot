---
name: quality-loop
description: >
  코드베이스 빅테크 95+ 품질 자동 개선 루프.
  2026-05-18 통합: 본 command 는 adversarial-review-loop skill 의 codebase mode 로 위임.
  Skill 이 13-dim rubric scoring + 병렬 contract fan-out + 재채점 loop 전체 실행.
  사용법: /quality-loop [--target 95] [--dimension TYPE_SAFETY] [--mode sequential|parallel]
argument-hint: "[--target 95] [--dimension <name>] [--mode sequential|parallel]"
allowed-tools: Skill
---

<objective>
adversarial-review-loop skill 의 codebase mode 호출 wrapper. 직접 호출 가능: 자연어 ("quality loop", "95점", "score this project") → skill auto-dispatch 됨.

이 command 는 인수 파싱 + skill 호출 + state 재개 처리 책임만 짊.
</objective>

<context>
Arguments: $ARGUMENTS

Flag 파싱:
  --target N         목표 weighted_score (기본: 95)
  --dimension X      특정 차원만 (기본: 전체 13 차원)
  --mode             sequential (PR 머지 후 다음, 기본) | parallel (fan-out, conflict risk)
  --max-iterations   안전 한계 (기본: 10)

State file: {cwd}/.planning/quality/score-state.json (재개 가능)
Project config: {cwd}/.quality-loop.json (선택, language/cmd/exclude 오버라이드)
</context>

<process>

1. **Arguments parse** — flag 추출, state file 존재 시 resume 여부 묻기.

2. **Skill dispatch** — `Skill("adversarial-review-loop", args="mode=codebase target=<N> dimension=<X> parallel=<mode>")` 호출.

3. **Skill 완료 대기** — codebase mode state machine 이 INIT → ANALYZE → EVALUATE → APPROVE → EXECUTE → RESCORE → CHECK 순회. 사용자 gate (APPROVE) 에서 멈추고 입력 받음.

4. **결과 반환** — 최종 weighted_score, history 변화, 미해소 contracts.

</process>

<note>
이전 standalone /quality-loop 의 전체 state machine 본문은 ~/.claude/skills/adversarial-review-loop/SKILL.md 의 "# codebase mode" 섹션으로 이전됨. 본 command 파일은 thin wrapper.

quality-eval skill (13-dim rubric data) 은 codebase mode 가 EVALUATE/RESCORE 단계에서 reference 로 사용. 독립 호출도 가능 (rubric 자체만 보고 싶을 때).
</note>

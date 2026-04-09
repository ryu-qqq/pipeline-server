---
name: pipeline
description: |
  에이전트 파이프라인을 실행하는 오케스트레이터 스킬.
  전체 파이프라인 실행, 특정 레이어 실행, 특정 단계 실행, 산출물 검증, 상태 확인을 지원한다.
  "파이프라인", "pipeline", "전체 실행", "전체 빌드", "도메인 실행",
  "빌드 실행", "리뷰 실행", "테스트 실행", "감사", "audit",
  "상태 확인", "status", "파이프라인 돌려줘" 등의 요청에 사용한다.
allowed-tools:
  - Read
  - Write
  - Glob
  - Grep
  - Bash
  - Agent
---

# Pipeline Orchestrator Skill

## 개요

에이전트 파이프라인의 **사용자 진입점**이다.
사용자의 커맨드를 파싱하여 각 레이어별 하네스를 순서대로 호출하고,
에이전트 실행 중 사용자 의사결정이 필요한 시점에 중계 역할을 한다.

---

## 지원 커맨드

| 커맨드 | 설명 | 예시 |
|--------|------|------|
| `run` | 전체 파이프라인 실행 (Phase 0~5) | `/pipeline run` |
| `layer <layer>` | 특정 레이어만 실행 | `/pipeline layer domain` |
| `step <step> <layer>` | 특정 단계만 실행 | `/pipeline step build domain` |
| `audit` | project-manager 산출물 검증 | `/pipeline audit` |
| `status` | 현재 파이프라인 상태 확인 | `/pipeline status` |

### 파라미터 값

**layer:** `domain`, `service`, `persistence`, `infra`

**step:** `build`, `review`, `test`

---

## 자연어 매핑

사용자가 슬래시 커맨드 대신 자연어로 요청할 수 있다:

| 자연어 | 파싱 결과 |
|--------|----------|
| "전체 파이프라인 돌려줘" | command=run |
| "도메인 빌드해줘" | command=step, step=build, layer=domain |
| "서비스 리뷰 실행" | command=step, step=review, layer=service |
| "영속성 레이어 실행" | command=layer, layer=persistence |
| "지금 상태 어때?" | command=status |
| "산출물 검증해줘" | command=audit |

---

## 실행 흐름

### 1. 커맨드 파싱

사용자 입력을 구조화된 지시문으로 변환한다:

```markdown
## 파이프라인 실행 요청
- command: {run | layer | step | audit | status}
- layer: {domain | service | persistence | infra | all}
- step: {build | review | test | all}
```

### 2. 시작 전 확인 (run, layer, step)

사용자에게 실행 범위를 확인한다:

```
파이프라인을 실행합니다.
- 모드: {전체 실행 / domain 레이어만 / domain build 단계만}
- 컨벤션: docs/convention-python-ddd.md ✅
- 아키텍처: docs/design-architecture.md ✅
계속할까요?
```

### 3. 레이어별 하네스 호출

`run` 커맨드는 아래 순서로 4개 하네스를 호출한다:

```
Phase 0: 전제조건 확인 (문서 존재, 린트 설정)
         ↓
Phase 1: /domain-harness build
         domain-builder → code-reviewer + convention-guardian → FIX → unit-test-designer
         ↓ (PASS 시)
Phase 2: /service-harness build
         service-builder → code-reviewer + convention-guardian → FIX → unit-test-designer
         ↓ (PASS 시)
Phase 3: [병렬]
         /persistence-harness build
         /infra-harness build
         persistence-builder + infra-builder → code-reviewer + convention-guardian → FIX → integration-test-designer
         ↓ (모두 PASS 시)
Phase 4: /pipeline audit
         project-manager 산출물 감사
         ↓ (PASS 시)
Phase 5: 완료 보고
```

**순서 의존성**: Phase 1 → 2 → 3은 순차 (레이어 간 의존성). Phase 3 내부는 병렬.

### 4. ESCALATION 중계

하네스에서 ESCALATION이 발생하면 사용자에게 전달:

```
## ESCALATION 발생 — {레이어}

FIX 루프 {N}/{최대}회 소진. 미해결 이슈가 있습니다.

### 문제 요약
{code-reviewer 또는 convention-guardian의 미해결 지적}

### 선택지
A) {방향 A} — {설명}
B) {방향 B} — {설명}
C) 직접 방향을 지정

어떤 방향으로 진행할까요?
```

사용자 응답을 받아 해당 하네스에 전달 → 수정 → 재검증.

### 5. 완료 보고

```
## 파이프라인 완료

| 레이어 | 상태 | FIX 횟수 | 비고 |
|--------|:----:|:-------:|------|
| Domain | DONE | 1 | code-reviewer에서 1회 수정 |
| Service | DONE | 0 | |
| Persistence | DONE | 1 | 인덱스 순서 수정 |
| Infra | DONE | 0 | |

에스컬레이션: 0건
컨벤션 이의: 0건
산출물 감사: PASS

Ruff: ✅ (전체 통과)
테스트: ✅ (domain 18 + application 22 + adapter 33 = 73개 통과)
```

### 6. status 커맨드

현재 어떤 Phase가 완료/진행 중/대기인지 보고:

```
## 파이프라인 상태

| Phase | 레이어 | 상태 | FIX |
|-------|--------|:----:|:---:|
| Phase 1 | Domain | COMPLETED | 1/3 |
| Phase 2 | Service | IN_PROGRESS | 0/2 |
| Phase 3 | Persistence | NOT_STARTED | - |
| Phase 3 | Infra | NOT_STARTED | - |
| Phase 4 | Audit | NOT_STARTED | - |

전체 상태: IN_PROGRESS
```

### 7. audit 커맨드

project-manager 에이전트를 호출하여 산출물 감사 실행:

```
Agent 도구 호출:
  subagent_type: project-manager
  description: "산출물 감사"
  prompt: |
    산출물 감사를 실행하세요.
    에이전트 정의: .claude/agents/project-manager.md
```

---

## 주의사항

- `run` 커맨드는 Phase 1 → 2 → 3 순서를 반드시 지킨다 (레이어 의존성)
- 각 Phase가 FAIL이면 다음 Phase로 진행하지 않는다
- ESCALATION 대기 중에는 사용자 응답 없이 다음 Phase로 진행하지 않는다
- `layer` 커맨드는 해당 레이어의 하네스만 독립 실행한다
- `step` 커맨드는 하네스의 특정 모드(build/review/test)만 실행한다

# AI 에이전트 시스템 분석 — ota-toy 프로젝트 참조

> 목적: pipeline-server 프로젝트에 멀티 에이전트 시스템을 구축하기 위한 기반 자료
> 참조: ryu-qqq/ota-toy (.claude/agents/, .claude/skills/, docs/ai-usage-log.md)

---

## 1. ota-toy 에이전트 체계 요약

### 규모
- 27개 에이전트, 7개 스킬
- Java 21 + Spring Boot + Hexagonal 멀티모듈 프로젝트

### 역할 분류 체계

| 계층 | 에이전트 수 | 역할 |
|---|---|---|
| 전략/기획 | 3 | product-owner, project-lead, project-manager |
| 오케스트레이션 | 2 | pipeline-orchestrator, agent-recruiter |
| 빌더(Build) | 5 | domain/application/rest-api/persistence-mysql builder |
| 리뷰어(Review) | 5 | code-reviewer, spec-reviewer, application-reviewer 등 |
| 테스터(Test) | 4 | domain/application/persistence/rest-api test-designer |
| 하네스(Harness) | 4 | 레이어별 빌드→리뷰→FIX→테스트 자동화 |
| 컨벤션 관리 | 3 | convention-guardian, convention-advocate, dependency-guardian |
| 기타 | 1 | journal-recorder (의사결정 기록) |

### 핵심 패턴: "생성 → 검증 → 피드백 루프"

```
Builder (생성) → Reviewer (검증) → FIX-REQUEST → Builder (수정) → Reviewer (재검증)
                                         ↓ (최대 N회 초과)
                                    ESCALATION → project-lead → 사용자 의사결정
```

### 피드백 채널 5가지

| 채널 | 방향 | 용도 |
|---|---|---|
| FIX-REQUEST/RESPONSE | reviewer → builder | 코드 수정 |
| ESCALATION | builder FIX 초과 → project-lead → 사용자 | 해결 불가 |
| CONVENTION-DISPUTE | builder → advocate → guardian | 컨벤션 이의 |
| AUDIT-REQUEST | project-manager → builder | 산출물 보완 |
| CLARIFY-REQUEST | builder → product-owner | 요구사항 명확화 |

### 파이프라인 구조 (Phase 0~5)

```
Phase 0: 전제조건 확인 (백로그, ERD, 컨벤션 존재)
Phase 1: Domain (builder → [병렬] code-reviewer + spec-reviewer → FIX → test-designer)
Phase 2: Application (builder → reviewer → FIX → test-designer)
Phase 3: [병렬] Adapter-out(persistence) + Adapter-in(rest-api)
Phase 4: project-manager 산출물 감사
Phase 5: 완료 보고 (state.yaml COMPLETED)
Phase E: ESCALATION (FIX 초과)
Phase D: CONVENTION-DISPUTE (컨벤션 이의)
```

---

## 2. pipeline-server에 적용할 에이전트 설계

### 과제 규모에 맞는 축소 (27개 → 예상 10~12개)

ota-toy는 7개 Bounded Context의 대규모 프로젝트. pipeline-server는 단일 컨텍스트의 과제.
27개를 전부 만들 필요 없지만, **핵심 패턴은 유지**해야 함.

### 필요한 에이전트 역할 (추천)

| 역할 | 에이전트명 | 설명 |
|---|---|---|
| **기획** | product-owner | 과제 요구사항 → 백로그 분석 |
| **설계** | project-lead | 아키텍처 결정 + 컨벤션 관리 |
| **PM** | project-manager | 산출물 검증 + Day 일정 관리 |
| **도메인 빌더** | domain-builder | Domain 모델, VO, Enum, Exception 생성 |
| **도메인 리뷰어** | domain-reviewer | 도메인 컨벤션 검증 (DDD 규칙) |
| **서비스 빌더** | service-builder | Service, Parser, Validator 생성 |
| **어댑터 빌더** | adapter-builder | Entity, Repository, Router, Schema 생성 |
| **테스트 설계** | test-designer | 모든 레이어 테스트 설계 + 코드 |
| **컨벤션 수호** | convention-guardian | Python DDD 컨벤션 검증 (Ruff 규칙) |
| **파이프라인** | pipeline-orchestrator | 전체 흐름 관리 |
| **기록** | journal-recorder | AI 활용 기록 + 의사결정 추적 |
| **에이전트 모집** | agent-recruiter | 새 에이전트 생성 |

### ota-toy와의 차이점

| 항목 | ota-toy (Java) | pipeline-server (Python) |
|---|---|---|
| 컨벤션 강제 | ArchUnit (빌드 시 자동) | Ruff (린트 시 자동) |
| 레이어 | 4개 (Domain/App/Adapter-in/Adapter-out) | 동일하지만 파이썬 관례 적용 |
| 테스트 | JUnit + MockMvc + Testcontainers | pytest + TestClient + SQLite in-memory |
| 저장소 | MySQL 단일 | MySQL + MongoDB + Redis (Polyglot) |
| 비동기 | 없음 | Celery Worker |
| 빌드 검증 | `./gradlew compileJava` | `ruff check + ruff format` |

---

## 3. AI 활용 패턴 분석 (사용자의 작업 스타일)

### 사용자의 AI 활용 원칙

1. **"AI는 생성, 사람은 판단"**
   - AI가 제안한 것과 본인이 판단한 것을 분리
   - "왜 이걸 선택했는가"를 항상 기록

2. **"컨벤션 우선"**
   - 코드보다 컨벤션을 먼저 확립
   - 컨벤션이 있어야 AI가 규칙 안에서 제대로 동작한다는 철학

3. **"점진적 진행"**
   - 전체를 한 번에 하지 않고 레이어별로 논의하며 진행
   - 각 단계를 이해하면서 가고 싶어함

4. **"Java 경험을 Python에 대응"**
   - 헥사고날, DDD, CQRS 등의 원칙을 유지하되 파이썬 관례에 맞게 변환
   - "파이썬은 원래 이렇게 하느냐" 질문을 통해 관례를 학습

5. **"구조적 감시"**
   - 코드 리뷰를 에이전트에게 위임
   - 컨벤션 위반을 자동으로 감지하는 시스템 선호

### 사용자가 중시하는 것

- DDD 순수 도메인 (VO, Rich Domain Model, 예외 계층)
- 레이어 격리 (의존성 방향 엄격 준수)
- 네이밍 일관성
- 저장소별 패키지 분리
- 테스트 커버리지
- 문서화 (설계 근거, 의사결정 추적)

---

## 4. 에이전트 구축에 필요한 기반 자료

### 컨벤션 문서 (이미 작성됨)
- `docs/convention-python-ddd.md` — Python DDD 컨벤션 (DOM/APP/ADP/DI/TST/FBD 규칙)

### 레퍼런스 리서치 (이미 작성됨)
- `docs/research-python-ddd.md` — 6개 레퍼런스 프로젝트 분석 + 패턴 비교표

### 설계 문서 (이미 작성됨)
- `docs/design-architecture.md` — CQRS + Polyglot Persistence 아키텍처

### 데이터 분석 (이미 작성됨)
- `docs/data-analysis.md` — 3개 파일 노이즈 분석 + 정제 정책

### 아직 필요한 것
- `docs/backlog.md` — 과제 요구사항 → 백로그 변환 (product-owner가 할 일)
- `.claude/agents/` — 에이전트 정의 파일 (agent-recruiter가 할 일)
- `.claude/skills/` — 스킬 정의 파일
- `tests/` — 테스트 코드 (test-designer가 할 일)
- `README.md` — 최종 제출물

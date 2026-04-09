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

### 과제 규모에 맞는 축소 (27개 → 14개)

ota-toy는 7개 Bounded Context의 대규모 프로젝트. pipeline-server는 단일 컨텍스트의 과제.
27개를 전부 만들 필요 없지만, **핵심 패턴은 유지**해야 함.
초기 12개에서 리뷰/빌더/테스트 편중 피드백을 반영하여 14개로 보강.

### 에이전트 조직 (최종 14개)

| 계층 | 에이전트명 | 설명 |
|---|---|---|
| **기획** | product-owner | 과제 요구사항 → 백로그 분석 |
| **설계** | project-lead | 아키텍처 결정 + 컨벤션 관리 |
| **PM** | project-manager | 산출물 검증 + Day 일정 관리 |
| **빌더** | domain-builder | Domain 모델, VO, Enum, Exception, Port 생성 |
| **빌더** | service-builder | Service, Parser, Validator 생성 |
| **빌더** | persistence-builder | MySQL + MongoDB 데이터 접근 구현 |
| **빌더** | infra-builder | Redis, Celery, REST, Worker, DI, Docker 구현 |
| **리뷰** | code-reviewer | 전 레이어 설계 적절성 리뷰 |
| **컨벤션** | convention-guardian | Python DDD 컨벤션 + Ruff 규칙 검증 |
| **테스트** | unit-test-designer | Domain + Application 단위 테스트 |
| **테스트** | integration-test-designer | Adapter 통합/E2E 테스트 |
| **파이프라인** | pipeline-orchestrator | 전체 흐름 관리 |
| **기록** | journal-recorder | AI 활용 기록 + 의사결정 추적 |
| **메타** | agent-recruiter | 새 에이전트 생성/수정/조직 관리 |

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
- `.claude/skills/` — 스킬 정의 파일
- `tests/` — 테스트 코드 (test-designer가 할 일)
- `README.md` — 최종 제출물

### 완료된 것
- `.claude/agents/` — 14개 에이전트 정의 파일 (2026-04-09 채용 완료, 보강 반영)

---

## 5. 에이전트 채용 결정 기록

> 작성일: 2026-04-09
> 결정자: agent-recruiter + 사용자
> 결과: ota-toy 27개 → pipeline-server 14개 (52% 축소)
> 이력: 초기 12개 → 사용자 피드백 반영 → 14개로 보강

### 왜 14개인가 — 축소 + 보강 근거

ota-toy는 **7개 Bounded Context**를 가진 대규모 멀티모듈 프로젝트였다.
pipeline-server는 **단일 컨텍스트**(자율주행 영상 데이터 정제)의 과제다.

초기 12개로 채용했으나, 사용자 피드백으로 아래 편중 문제가 드러나 14개로 보강했다:
- 도메인 외 레이어의 리뷰어 부재 (서비스, 어댑터)
- adapter-builder 1명이 6개 기술을 담당하는 과부하
- test-designer 1명이 전 레이어를 담당하는 과부하

| 비교 항목 | ota-toy | pipeline-server | 비율 |
|---|---|---|---|
| Bounded Context 수 | 7개 | 1개 | 1/7 |
| 모듈 수 | 14개 (settings.gradle.kts) | 1개 (app/) | 1/14 |
| 에이전트 수 | 27개 | 14개 | 52% |
| 빌더 | 5개 (레이어별 1개 + 어댑터별) | 4개 (domain/service/persistence/infra) | 80% |
| 리뷰어 | 5개 (code/spec/application 분리) | 2개 (code-reviewer + convention-guardian) | 40% |
| 테스터 | 4개 (레이어별 1개) | 2개 (unit + integration) | 50% |
| 하네스 | 4개 | 0개 (orchestrator가 대체) | 0% |
| 컨벤션 | 3개 (guardian/advocate/dependency) | 1개 (guardian만) | 33% |

핵심 원칙: **"생성 → 검증 → 피드백 루프" 패턴은 유지하되, 에이전트 수는 컨텍스트 규모에 비례시킨다.**

---

### 채용한 에이전트 14개 — 각각의 채용 이유

#### 전략 계층 (3개) — 그대로 유지

| 에이전트 | 채용 이유 |
|---|---|
| **product-owner** | 과제 요구사항을 백로그로 변환하는 역할은 프로젝트 규모와 무관하게 필요. API 4개, 파이프라인 3-Phase, Polyglot 저장소 등 요구사항이 단순하지 않아서 체계적 정리가 필수. |
| **project-lead** | 에스컬레이션 중재자가 없으면 Builder-Reviewer 피드백 루프가 교착 상태에 빠진다. 또한 Hexagonal + CQRS + Polyglot이라는 아키텍처 결정을 검증할 주체가 필요. Java→Python 전환 과정에서 "이 원칙을 Python에서도 유지해야 하는가"라는 판단이 빈번히 발생. |
| **project-manager** | Day 1~5 일정 관리 + 산출물 감사. 코드/테스트/문서/인프라가 모두 갖춰졌는지 기계적으로 확인하는 역할. 이것 없이는 "다 했다고 생각했는데 빠진 게 있었다"가 반복됨. |

#### 오케스트레이션 계층 (2개) — 그대로 유지

| 에이전트 | 채용 이유 |
|---|---|
| **pipeline-orchestrator** | Phase 0~5 흐름 관리자. 없으면 "지금 누가 무엇을 해야 하는지" 혼란. Domain→Application→Adapter 의존성 순서를 강제하는 역할. ota-toy에서 하네스(4개)가 하던 레이어별 자동화를 이 하나의 에이전트가 흡수. |
| **agent-recruiter** | 에이전트 자체를 관리하는 메타 에이전트. 프로젝트 진행 중 "이 역할이 추가로 필요하다"는 상황 대응. 실제로 이번에도 초기 12개에서 피드백 반영으로 14개로 보강하는 데 사용됨. |

#### 빌드 계층 (4개) — 5개 → 4개로 축소

| 에이전트 | 채용 이유 |
|---|---|
| **domain-builder** | 도메인 레이어는 프로젝트의 핵심. frozen dataclass, VO, ABC Port, 예외 계층 등 Python DDD 특유의 패턴이 많아서 전용 빌더가 필요. 다른 레이어와 달리 "비즈니스 의미를 코드로 표현"하는 창의적 작업이라 전문화가 가치 있음. |
| **service-builder** | Application 레이어는 "Port만 의존 + 전략 패턴 + CQRS 분리"라는 고유한 규칙이 있음. 5개 서비스 + 파서 + 검증기를 일관된 패턴으로 생성해야 함. |
| **persistence-builder** | MySQL(SQLAlchemy) + MongoDB(PyMongo) 데이터 접근 전문. 쿼리 성능, 인덱스 설계, Entity/Document + Mapper 패턴, 벌크 연산 등 DB 전문성이 필요. 초기에는 adapter-builder로 통합했으나 6개 기술을 1명이 담당하는 것은 과부하로 판단하여 분리. |
| **infra-builder** | Redis(캐시), Celery(비동기), REST(FastAPI 라우터), Worker(Celery 태스크), DI(dependencies.py), Docker(docker-compose) 담당. 시스템 경계의 "동작하게 만드는" 역할로, 영속성과는 다른 인프라/DevOps 전문성 필요. |

**보강 판단**: 초기 adapter-builder 1개 → persistence-builder + infra-builder 2개로 분리.
- 근거: adapter-builder가 mysql/mongodb/redis/celery/rest/worker 6가지 기술을 혼자 담당하면서 **리뷰어도 없는 상태**였음. DB 전문성(쿼리, 인덱스)과 인프라 전문성(캐시 전략, 컨테이너)은 성격이 다름.
- 분리 기준: "데이터를 어떻게 저장하는가"(persistence) vs "시스템이 어떻게 동작하는가"(infra)

#### 리뷰 계층 (2개) — 5개 → 2개로 축소하되, 범위 확장

| 에이전트 | 채용 이유 |
|---|---|
| **code-reviewer** | 초기에는 domain-reviewer로 도메인만 리뷰했으나, **전 레이어 설계 리뷰**로 확장. 도메인(VO, Rich Domain), 서비스(트랜잭션 경계, CQRS 분리), 어댑터(쿼리 성능, 인덱스, 캐시 전략) 모두 커버. convention-guardian이 "규칙 준수"를 기계적으로 검증한다면, code-reviewer는 "설계 적절성"을 판단적으로 리뷰. |
| **convention-guardian** | Python DDD 컨벤션(DOM/APP/ADP/DI/TST/FBD) 30개 규칙을 자동 검증. grep/ruff 기반으로 기계적 판단 가능한 영역. |

**보강 판단**: domain-reviewer → code-reviewer로 범위 확장.
- 근거: service-builder가 만든 코드의 설계 적절성(트랜잭션 경계, CQRS 분리)을 판단할 주체가 없었음. convention-guardian은 기계적 규칙만 검증 가능. code-reviewer가 전 레이어를 커버하면 별도 service-reviewer, adapter-reviewer를 채용하지 않아도 됨.
- **역할 분담 명확화**: convention-guardian="규칙을 지키는가"(자동화 가능) / code-reviewer="설계가 적절한가"(판단 필요). 둘 다 통과해야 PASS.

#### 테스트 계층 (2개) — 4개 → 2개로 축소

| 에이전트 | 채용 이유 |
|---|---|
| **unit-test-designer** | Domain(순수 단위, Mock 없음) + Application(Mock Repository) 테스트 전담. 테스트 피라미드의 하단(빠른 피드백) 담당. DDD 지식 필요 — VO 경계값, Rich Domain 행동 검증, 파서 전략 검증 등. |
| **integration-test-designer** | Adapter(SQLite in-memory, TestClient) + E2E(전체 시나리오) 테스트 전담. 인프라 지식 필요 — DB 세션 관리, DI 오버라이드, HTTP 상태 코드, 제약 조건 검증 등. |

**보강 판단**: test-designer 1개 → unit-test-designer + integration-test-designer 2개로 분리.
- 근거: 1명이 전 레이어를 담당하면 "Domain 순수 단위"와 "Adapter DB 통합" 사이의 컨텍스트 스위칭이 크고, 품질이 떨어짐. 두 영역은 필요한 전문성이 다름.
- 분리 기준: "Mock으로 격리하는 빠른 테스트"(unit) vs "실제 인프라에 연결하는 느린 테스트"(integration). 테스트 피라미드의 계층과 일치.

#### 컨벤션 계층 (1개) — 3개 → 1개로 축소

| 에이전트 | 채용 이유 |
|---|---|
| **convention-guardian** | (리뷰 계층과 겸임) 컨벤션 규칙 검증의 단일 책임점. |

**미채용 판단**:
- **convention-advocate** (미채용): ota-toy에서는 Builder가 DISPUTE를 제기하면 advocate가 중재하고 guardian이 최종 판단하는 3자 구조였음. pipeline-server에서는 Builder → guardian → project-lead로 2자 구조로 단순화. 중간 중재자 없이도 피드백 루프가 작동함.
- **dependency-guardian** (미채용): ota-toy에서는 모듈 간 의존성을 ArchUnit으로 검증했으나, pipeline-server는 단일 app/ 패키지 + Ruff로 충분. 모듈 경계가 없으므로 별도 의존성 감시 불필요.

#### 기록 계층 (1개) — 그대로 유지

| 에이전트 | 채용 이유 |
|---|---|
| **journal-recorder** | 사용자의 핵심 원칙 중 하나가 "AI는 생성, 사람은 판단" + "왜 이걸 선택했는가를 항상 기록". 이 철학을 시스템화한 에이전트. ADR(Architecture Decision Record), AI 활용 로그, 컨벤션 변경 이력을 체계적으로 관리. |

---

### 채용하지 않은 역할 — 각각의 미채용 이유

#### ota-toy에서 존재했으나 pipeline-server에서 미채용한 역할 (12개)

| 미채용 역할 | 미채용 이유 | 대체 |
|---|---|---|
| **domain-code-reviewer** | code-reviewer로 통합. 전 레이어 설계 리뷰를 1명이 담당. | code-reviewer |
| **domain-spec-reviewer** | code-reviewer로 통합. | code-reviewer |
| **application-reviewer** | code-reviewer가 Application 설계도 리뷰 (트랜잭션 경계, CQRS 분리). | code-reviewer |
| **application-builder** | service-builder로 명칭 변경. Python에서는 "Service"가 더 자연스러운 네이밍. | service-builder |
| **domain-test-designer** | unit-test-designer로 통합 (Domain + Application 단위 테스트). | unit-test-designer |
| **application-test-designer** | unit-test-designer로 통합. | unit-test-designer |
| **persistence-mysql-test-designer** | integration-test-designer로 통합 (Adapter 통합 테스트). | integration-test-designer |
| **rest-api-test-designer** | integration-test-designer로 통합. | integration-test-designer |
| **domain-harness-orchestrator** | pipeline-orchestrator가 흡수. 단일 BC에서 레이어별 하네스는 과도. | pipeline-orchestrator |
| **application-harness-orchestrator** | pipeline-orchestrator가 흡수. | pipeline-orchestrator |
| **persistence-harness-orchestrator** | pipeline-orchestrator가 흡수. | pipeline-orchestrator |
| **rest-api-harness-orchestrator** | pipeline-orchestrator가 흡수. | pipeline-orchestrator |
| **dependency-guardian** | 단일 패키지 구조 + Ruff로 충분. 모듈 간 의존성 감시 불필요. | convention-guardian (FBD 규칙) |

#### 축소 + 보강 패턴 요약

| 패턴 | 적용 | 증감 |
|---|---|---|
| **하네스 → orchestrator 흡수** | 4개 하네스 → pipeline-orchestrator 1개 | -4 |
| **테스트 레이어별 → 2분할** | 4개 → unit + integration | -2 |
| **리뷰어 세분화 → 전체 리뷰어** | 5개 → code-reviewer + convention-guardian | -3 |
| **어댑터 통합 → 2분할** | 3개 → persistence-builder + infra-builder | -1 |
| **중간 계층 제거** | convention-advocate + dependency-guardian | -2 |
| **명칭 변경** | application-builder → service-builder | 0 |
| **합계** | 27 → 14 | **-13** |

#### 보강 이력 (12개 → 14개)

| 변경 | 이전 | 이후 | 이유 |
|---|---|---|---|
| 리뷰어 범위 확장 | domain-reviewer (도메인만) | code-reviewer (전 레이어) | 서비스/어댑터 설계 리뷰 부재 해소 |
| 어댑터 빌더 분리 | adapter-builder 1개 (6기술) | persistence-builder + infra-builder | DB 전문성과 인프라 전문성은 별도 |
| 테스트 분리 | test-designer 1개 (전 레이어) | unit-test-designer + integration-test-designer | Mock 단위 vs 실제 DB 통합은 성격이 다름 |

---

### 추가 채용이 필요해질 수 있는 시나리오

현재 14개로 운영하되, 아래 상황에서는 추가 분리를 검토한다:

| 시나리오 | 분리 후보 | 트리거 |
|---|---|---|
| MongoDB와 MySQL 구현이 크게 달라짐 | persistence-builder → mysql-builder + mongodb-builder | 두 저장소 간 FIX-REQUEST 패턴이 완전히 다름 |
| Celery 워커 로직이 복잡해짐 | infra-builder에서 worker-builder 분리 | 비동기 태스크 종류 3개 이상 |
| E2E 테스트 전략이 독립적으로 필요 | integration-test-designer에서 e2e-test-generator 분리 | docker-compose 기반 시나리오 테스트 요구 |
| code-reviewer 부하 과다 | code-reviewer → domain-reviewer + service-reviewer 분리 | 리뷰 보고서가 3개 레이어 합쳐서 50줄 초과 |

agent-recruiter가 이 목록을 참조하여 "분리가 필요한 시점"을 판단한다.

---

## 6. 조직 변경 이력

### 변경 #1: 초기 채용 (2026-04-09)

> 결정자: agent-recruiter
> 결과: 12개 에이전트 채용

ota-toy(27개)를 기반으로 단일 BC 규모에 맞춰 축소 설계.
"생성 → 검증 → 피드백 루프" 핵심 패턴은 유지하되 에이전트 수를 컨텍스트 규모에 비례시키는 원칙 적용.

| 계층 | 채용된 에이전트 |
|---|---|
| 전략 | product-owner, project-lead, project-manager |
| 오케스트레이션 | pipeline-orchestrator, agent-recruiter |
| 빌드 | domain-builder, service-builder, adapter-builder |
| 리뷰 | domain-reviewer, convention-guardian |
| 테스트 | test-designer |
| 기록 | journal-recorder |

---

### 변경 #2: 리뷰/빌더/테스트 편중 보강 (2026-04-09)

> 결정자: 사용자 피드백 → agent-recruiter 반영
> 결과: 12개 → 14개 (+2 순증)

#### 피드백 원문 (사용자)

```
문제: 도메인 외 레이어의 리뷰/검증이 부족함

현재 편중 상태:
  도메인:   builder ✅ + reviewer ✅    ← 잘 구성됨
  서비스:   builder ✅ + reviewer ❌    ← 리뷰어 없음
  어댑터:   builder ✅ + reviewer ❌    ← 리뷰어 없음
  테스트:   designer 1명이 전 레이어    ← 과부하
  인프라:   아무도 없음                  ← Docker, Celery, Redis AOF

구체적 문제:
1. service-builder가 만든 코드의 설계 적절성을 누가 판단하나?
   (트랜잭션 경계, CQRS 분리 등) convention-guardian은 기계적 규칙만 검증 가능
2. adapter-builder가 6개 기술(mysql/mongodb/redis/celery/rest/worker)을 혼자 다 하는데
   리뷰어가 없음. 쿼리 성능, 인덱스 설계, 캐시 전략 등 기술별 전문성이 필요
3. test-designer 1명이 domain 단위 + API 통합 + E2E를 다 하면 품질 떨어짐
```

#### 분석

| 피드백 | 핵심 원인 | 판단 |
|---|---|---|
| 서비스/어댑터 리뷰어 부재 | domain-reviewer가 도메인만 커버. "설계 적절성" 판단은 convention-guardian의 역할 밖 | domain-reviewer를 code-reviewer로 확장하여 전 레이어 설계 리뷰 |
| adapter-builder 과부하 | 6개 기술(mysql/mongodb/redis/celery/rest/worker)을 1명이 담당 + 리뷰어 없음 | DB 전문성 vs 인프라 전문성은 성격이 다름 → 2개로 분리 |
| test-designer 과부하 | "순수 단위 테스트"와 "DB 통합 테스트"는 필요 전문성이 다름 | 테스트 피라미드 계층에 맞춰 2개로 분리 |

사용자의 보강 제안 3가지 중 검토 결과:

| 사용자 제안 | 채택 여부 | 이유 |
|---|---|---|
| service-reviewer 추가 또는 domain-reviewer 확장 | **domain-reviewer를 code-reviewer로 확장** 채택 | 별도 service-reviewer를 추가하면 adapter-reviewer도 필요해져서 +2. 1명이 전 레이어 설계를 판단하는 편이 일관된 시각 유지에 유리 |
| adapter-builder → persistence-builder + infra-builder 분리 | **그대로 채택** | "데이터를 어떻게 저장하는가" vs "시스템이 어떻게 동작하는가"는 명확한 분리 기준 |
| test-designer → unit + integration 분리 | **그대로 채택** | "Mock 격리 빠른 테스트" vs "실제 DB 느린 테스트"는 테스트 피라미드 계층과 일치 |

#### 변경 상세

**삭제 (3개)**:

| 삭제 에이전트 | 이유 |
|---|---|
| domain-reviewer | code-reviewer로 역할 확장 대체 |
| adapter-builder | persistence-builder + infra-builder로 분리 대체 |
| test-designer | unit-test-designer + integration-test-designer로 분리 대체 |

**신규 생성 (5개)**:

| 신규 에이전트 | 역할 | 이전 대비 변경 |
|---|---|---|
| code-reviewer | 전 레이어(Domain/Application/Adapter) 설계 적절성 리뷰 | domain-reviewer에서 범위 확장. Domain: VO·Rich Domain·예외 계층, Application: 트랜잭션 경계·CQRS 분리·서비스 책임, Adapter: 쿼리 성능·인덱스·캐시 전략 |
| persistence-builder | MySQL(SQLAlchemy) + MongoDB(PyMongo) 데이터 접근 | adapter-builder에서 DB 전문 영역 분리. Entity, Repository, Mapper, QueryBuilder, Document, Index 설계 |
| infra-builder | Redis + Celery + REST + Worker + DI + Docker | adapter-builder에서 인프라 영역 분리. 캐시, 비동기, 라우터, 스키마, DI 체인, 컨테이너 구성 |
| unit-test-designer | Domain + Application 단위 테스트 | test-designer에서 단위 테스트 분리. 순수 Python(Domain) + Mock(Application) |
| integration-test-designer | Adapter 통합 + E2E 시나리오 테스트 | test-designer에서 통합 테스트 분리. SQLite in-memory + TestClient + 전체 시나리오 |

**기존 에이전트 참조 갱신 (6개)**:

| 수정 에이전트 | 변경 내용 |
|---|---|
| domain-builder | `domain-reviewer` → `code-reviewer` 참조 변경 (리뷰 요청 대상, FIX-REQUEST 수신처, 관계 섹션) |
| service-builder | `code-reviewer` 관계 추가 (설계 리뷰 요청), `adapter-builder` → `persistence-builder, infra-builder` 참조 변경 |
| convention-guardian | Builder 목록에서 `adapter-builder` → `persistence-builder, infra-builder` 변경, `domain-reviewer` → `code-reviewer` 교차 검증 |
| pipeline-orchestrator | Phase 1~3 흐름 전면 갱신: 각 Phase에 code-reviewer 리뷰 추가, Phase 3 빌더 분리, 테스트 에이전트 분리 반영 |
| agent-recruiter | 조직표 전면 갱신 (14개 반영), 팀 구성 템플릿 → 피드백 루프 쌍 테이블로 변경 |
| docs/ai-agent-analysis.md | 섹션 2(조직표), 섹션 5(채용 기록) 전면 갱신 |

#### 변경 전후 비교

**피드백 루프 구조 변경**:

```
[변경 전]
domain-builder → domain-reviewer + convention-guardian    (리뷰 있음)
service-builder → convention-guardian만                   (설계 리뷰 없음 ❌)
adapter-builder → convention-guardian만                   (설계 리뷰 없음 ❌)

[변경 후]
domain-builder      → code-reviewer + convention-guardian (리뷰 있음 ✅)
service-builder     → code-reviewer + convention-guardian (리뷰 있음 ✅)
persistence-builder → code-reviewer + convention-guardian (리뷰 있음 ✅)
infra-builder       → code-reviewer + convention-guardian (리뷰 있음 ✅)
```

**테스트 커버리지 변경**:

```
[변경 전]
test-designer 1명 → Domain 단위 + Application Mock + Adapter DB + E2E (과부하)

[변경 후]
unit-test-designer        → Domain 순수 단위 + Application Mock (빠른 피드백)
integration-test-designer → Adapter SQLite + API TestClient + E2E (인프라 검증)
```

**Phase별 에이전트 배치 변경**:

| Phase | 변경 전 | 변경 후 |
|---|---|---|
| Phase 1 (Domain) | domain-builder → domain-reviewer + guardian | domain-builder → code-reviewer + guardian → unit-test-designer |
| Phase 2 (Application) | service-builder → guardian만 | service-builder → code-reviewer + guardian → unit-test-designer |
| Phase 3 (Adapter) | adapter-builder 1명 → guardian만 | persistence-builder + infra-builder (병렬) → code-reviewer + guardian → integration-test-designer |

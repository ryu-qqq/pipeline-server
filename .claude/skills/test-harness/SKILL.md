---
name: test-harness
description: |
  테스트 전용 하네스. 분석 → 시나리오 설계 → 테스트 생성 → 실행 → FIX 파이프라인을 강제 실행한다.
  "테스트 하네스", "test harness", "테스트 돌려줘", "테스트 분석",
  "누락 테스트 찾아줘", "테스트 보완", "커버리지 분석", "테스트 생성",
  "도메인 테스트", "서비스 테스트", "어댑터 테스트", "통합 테스트",
  "전체 테스트" 등의 요청에 사용한다.
---

# 테스트 하네스

## 개요

테스트 품질을 **파이프라인으로 강제**하는 전용 하네스.
"분석 → 설계 → 생성 → 실행 → FIX"를 빠짐없이 수행한다.

기존 하네스(domain-harness, service-harness 등)가 "빌드 → 린트 → 리뷰 → 테스트" 전체를 다룬다면,
이 하네스는 **테스트에만 집중**하여 더 깊은 커버리지 분석과 시나리오 설계를 수행한다.

---

## 실행 모드

### 모드 1: 분석 (`/test-harness analyze {레이어}`)
기존 테스트의 커버리지를 분석하고 누락 시나리오를 보고한다. 코드는 수정하지 않는다.

```
/test-harness analyze domain
/test-harness analyze application
/test-harness analyze adapter
/test-harness analyze all
```

### 모드 2: 테스트 (`/test-harness test {레이어}`)
누락 시나리오를 찾고 테스트 코드를 생성한 뒤 실행까지 완료한다.

```
/test-harness test domain
/test-harness test application
/test-harness test adapter
/test-harness test integration
/test-harness test all
```

### 모드 3: 실행만 (`/test-harness run {레이어}`)
기존 테스트를 실행하고 결과만 보고한다. 분석/생성 없음.

```
/test-harness run domain
/test-harness run application
/test-harness run all
```

---

## 레이어별 대상

| 레이어 | 앱 코드 | 테스트 경로 | pytest 명령 | 테스트 전략 |
|--------|---------|-----------|------------|-----------|
| domain | `app/domain/` | `tests/domain/` | `pytest tests/domain/ -v` | 순수 Python, Mock 없음 |
| application | `app/application/` | `tests/application/` | `pytest tests/application/ -v` | Mock(spec=ABC) |
| adapter | `app/adapter/` | `tests/adapter/` | `pytest tests/adapter/ -v` | SQLite in-memory, TestClient |
| integration | 전체 앱 | `tests/integration/` | `pytest tests/integration/ -v` | Testcontainers (Docker 필요) |
| all | 전체 | `tests/` | `pytest tests/ -v --ignore=tests/integration` | 단위+어댑터 (integration 제외) |

---

## 시나리오 카테고리 체계

### Domain (T-1 ~ T-6)
| 코드 | 이름 | 검증 대상 |
|------|------|----------|
| T-1 | 생성 검증 | VO/Model __post_init__ 불변식, 경계값 |
| T-2 | 상태 전이 | AnalyzeTask/OutboxMessage 전이 체인 + 원본 불변 |
| T-3 | 불변식 | frozen=True 강제, FrozenInstanceError |
| T-4 | 도메인 로직 | is_hazardous, is_reliable 등 비즈니스 판단 |
| T-5 | VO 검증 | Temperature 범위, Confidence 범위, SourcePath 형식 |
| T-6 | 팩토리 | create_new, create_analyze_event 반환값 |

### Application (AT-1 ~ AT-6)
| 코드 | 이름 | 검증 대상 |
|------|------|----------|
| AT-1 | 정상 흐름 | 서비스 happy path, 반환값 |
| AT-2 | 실패 흐름 | ConflictError, DataNotFoundError 전파 |
| AT-3 | 호출 순서 | Mock verify — 의존성 호출 순서 |
| AT-4 | 트랜잭션 | @transactional, Outbox 저장 |
| AT-5 | 정제 로직 | Refiner valid/rejection 분리, 빈 dict, 다중 에러 |
| AT-6 | 파이프라인 | PhaseRunner 청크, INSERT IGNORE 중복, resume |

### Adapter (AIT-1 ~ AIT-6)
| 코드 | 이름 | 검증 대상 |
|------|------|----------|
| AIT-1 | Mapper 왕복 | domain ↔ entity 라운드트립 |
| AIT-2 | Repository CRUD | save/find/search + 페이지네이션 |
| AIT-3 | QueryBuilder | 동적 쿼리 조건 + SQL 컴파일 |
| AIT-4 | REST 정상 | 200/202 응답, 스키마 검증 |
| AIT-5 | REST 에러 | 409, 400, 422 에러 핸들링 |
| AIT-6 | REST 페이징 | offset(page) + cursor(after) 분기 |

### Integration (E2E-1 ~ E2E-5)
| 코드 | 이름 | 검증 대상 |
|------|------|----------|
| E2E-1 | 전체 흐름 | POST → Outbox → Pipeline → GET |
| E2E-2 | 중복 방어 | 409 Conflict + 재요청 허용 |
| E2E-3 | 데이터 품질 | Rejection 분류/필터링 |
| E2E-4 | Task 격리 | task_id별 데이터 독립 |
| E2E-5 | API 에러 | ProblemDetail RFC 7807 |

---

## 실행 시 이 스킬이 하는 것

1. 사용자 커맨드를 파싱한다 (모드 + 레이어)
2. `test-harness-orchestrator` 에이전트를 호출한다
3. 에이전트가 반환하는 중간 결과를 사용자에게 보고한다
4. FIX 루프 중 앱 코드 버그가 발견되면 사용자에게 보고한다
5. ESCALATION이 발생하면 사용자에게 선택지를 제시한다
6. 최종 결과를 시나리오 커버리지 매트릭스로 보고한다

---

## 파이프라인 상세

### analyze 모드

```
[Phase 1] 앱 코드 분석
  → 대상 레이어의 모든 파일을 읽고 분기/에러 경로 추출
  → 시나리오 카테고리별로 "테스트가 필요한 경로" 목록 생성

[Phase 2] 기존 테스트 분석
  → 기존 테스트 파일을 읽고 "이미 커버된 시나리오" 목록 생성
  → 테스트 클래스/함수명 + assert 대상으로 매핑

[Phase 3] Gap 분석 보고
  → Phase 1 - Phase 2 = 누락 시나리오
  → 카테고리별 커버리지 매트릭스 출력
  → 코드 수정 없음
```

### test 모드

```
[Phase 1~2] analyze 모드와 동일

[Phase 3] 테스트 코드 생성
  → domain/application → unit-test-designer 에이전트
  → adapter → integration-test-designer 에이전트
  → 기존 테스트 스타일에 맞춤

[Phase 4] 테스트 실행
  → pytest {대상} -v --tb=short
  → 전체 통과 = PASS

[Phase 5] FIX 루프 (최대 2회)
  → 테스트 버그 → 테스트 수정
  → 앱 코드 버그 → 사용자에게 보고
  → 재실행

[Phase 6] 결과 보고
  → 시나리오 커버리지 매트릭스
  → 테스트 실행 결과 (통과/실패/시간)
```

### run 모드

```
[Phase 1] 테스트 실행
  → pytest {대상} -v --tb=short

[Phase 2] 결과 보고
  → 통과/실패 수, 실행 시간
  → 실패 시 실패 테스트 상세
```

---

## 사용자 인터랙션 예시

### 분석 모드
```
사용자: /test-harness analyze domain

스킬: "도메인 테스트 커버리지를 분석합니다."

[Phase 1] 앱 코드 분석
  → app/domain/models.py: 분기 15개, 팩토리 2개, 상태 전이 8개
  → app/domain/value_objects.py: __post_init__ 7개, 메서드 12개

[Phase 2] 기존 테스트 분석
  → tests/domain/test_models.py: 46개 테스트
  → tests/domain/test_value_objects.py: 39개 테스트

[Phase 3] Gap 분석

| 카테고리 | 필요 | 커버 | 누락 |
|----------|:----:|:----:|:----:|
| T-1 생성 검증 | 12 | 10 | 2 |
| T-2 상태 전이 | 8 | 8 | 0 |
| T-3 불변식 | 4 | 3 | 1 |
| T-4 도메인 로직 | 10 | 10 | 0 |
| T-5 VO 검증 | 14 | 13 | 1 |
| T-6 팩토리 | 4 | 4 | 0 |

누락 시나리오:
- T-1: VideoId(float값) 거부, ObjectCount(float값) 거부
- T-3: AnalysisResult frozen 변경 시도
- T-5: Temperature 정확히 -90, 정확히 60 경계
```

### 테스트 모드
```
사용자: /test-harness test application

스킬: "Application 테스트 하네스를 시작합니다."

[Phase 1~2] 코드 + 기존 테스트 분석
  → 누락 시나리오 5건 발견

[Phase 3] unit-test-designer 호출
  → 5개 테스트 생성

[Phase 4] pytest tests/application/ -v
  → 42/42 통과 ✅ (0.08s)

"Application 테스트 하네스 완료. 전체 통과."

| 카테고리 | 기존 | 신규 | 합계 |
|----------|:----:|:----:|:----:|
| AT-1 정상 흐름 | 8 | 1 | 9 |
| AT-2 실패 흐름 | 4 | 2 | 6 |
| AT-3 호출 순서 | 3 | 0 | 3 |
| AT-4 트랜잭션 | 1 | 0 | 1 |
| AT-5 정제 로직 | 16 | 1 | 17 |
| AT-6 파이프라인 | 6 | 1 | 7 |
```

### ESCALATION
```
[Phase 5] FIX 루프 — Round 2/2 (최대 도달)
  → 여전히 1건 실패

스킬: "FIX 루프 2회를 소진했습니다. 미해결 이슈:"
      1. test_pipeline_resume_all_completed — PipelineService가
         last_completed_phase=AUTO_LABELING일 때 아무 Phase도 실행하지 않고
         빈 results dict로 _build_result 호출 → KeyError

      "어떻게 하시겠습니까?"
      A) PipelineService에 "모든 Phase 완료" 조건 분기를 추가
      B) 테스트를 TODO 처리하고 이슈로 남김
      C) 직접 방향을 지정

사용자: A로 가자
```

---

## 에이전트 호출 정보

이 스킬은 `test-harness-orchestrator` 에이전트를 호출할 때 아래 정보를 전달한다:

```
모드: {analyze | test | run}
레이어: {domain | application | adapter | integration | all}
앱 코드 경로: app/{layer}/
테스트 경로: tests/{layer}/
시나리오 카테고리: {T-1~T-6 | AT-1~AT-6 | AIT-1~AIT-6 | E2E-1~E2E-5}
```

---

## FIX 한도

| 단계 | 최대 FIX 횟수 |
|------|-------------|
| 테스트 FIX 루프 | 2회 |
| ESCALATION 후 추가 FIX | 1회 |

---

## 다른 하네스와의 관계

- **domain-harness** Phase 5~6 = 이 하네스의 test domain 모드와 동일
- **service-harness** Phase 5~6 = 이 하네스의 test application 모드와 동일
- **persistence-harness** Phase 5~6 = 이 하네스의 test adapter 모드와 동일

기존 하네스의 테스트 단계에서 이 하네스를 내부적으로 활용할 수 있다.
단독 실행 시에는 테스트에만 집중하여 **더 깊은 커버리지 분석**을 제공한다.

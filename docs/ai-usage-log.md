# AI 활용 기록

## 활용 개요

- **사용 도구**: Claude Code (Anthropic CLI) — Claude Opus 4.6
- **활용 방식**: 데이터 분석 → 설계 논의 → 코드 리뷰 → 리팩토링을 반복하며, 매 단계에서 직접 설계 판단을 수행
- **핵심 원칙**: AI가 생성한 코드를 그대로 사용하지 않고, "왜 이렇게 해야 하는지"를 논의한 후 구현 방향을 결정

---

## 활용 흐름

```
1. 데이터 탐색    — Jupyter Notebook으로 직접 분석, AI에게 분석 결과 해석 요청
2. 컨벤션 확립    — Python DDD 레퍼런스 6개 프로젝트 분석 → 채택/미채택 판단
3. 초기 구현      — AI가 코드 초안 생성 → 직접 리뷰하며 "이건 왜 이래?" 지적
4. 반복 리팩토링  — 파일 하나씩 읽으며 컨벤션 위반/설계 문제를 함께 수정
5. 테스트         — 테스트 프롬프트를 작성하여 다른 세션에서 병렬 실행
6. 문서           — docs/ 문서를 에이전트에 위임, 결과를 직접 리뷰
```

---

## 핵심 의사결정 기록

AI와의 대화에서 **직접 방향을 정하고 AI가 구현한** 주요 결정들입니다.

### 1. "Repository에서 비즈니스 로직을 빼라"

> **문제**: OutboxRepository에 `mark_published()`, `mark_failed()`, `increment_retry()` 등 상태 전이 메서드가 있었음
>
> **판단**: "도메인 객체가 자기 상태를 변경해야지, Repository가 `mark_published` 같은 비즈니스를 알면 안 된다. 조회 → 도메인 내부에서 변형 → 저장, 이 패턴으로 가자"
>
> **결과**: Repository를 `save(upsert)` + `find` 2개만 남기고, `OutboxMessage.mark_processing()`, `AnalyzeTask.start_processing()` 같은 도메인 메서드로 이동. TaskRepository도 동일하게 정리.

### 2. "중복 탐지를 왜 애플리케이션에서 하냐, DB에 위임해라"

> **문제**: OddValidator, LabelValidator에서 `Counter`로 중복을 탐지하고 있었음. 전체 데이터를 메모리에 올려야 하고, 건별 INSERT 재시도 루프도 있었음
>
> **판단**: "MySQL에 UNIQUE INDEX 걸고 INSERT IGNORE로 밀어넣으면 되는 거 아니냐. 왜 애플리케이션에서 Counter로 세냐"
>
> **결과**: 중복 탐지 코드 전부 삭제, MySQL UNIQUE + INSERT IGNORE로 교체. rowcount로 실제 적재 건수 파악.

### 3. "DELETE ALL 하지 마, 쌓아둬라"

> **문제**: 재분석 시 `_clear_mysql()`로 전체 데이터를 삭제하고 다시 INSERT
>
> **판단**: "삭제하면 과거 분석 이력이 날아가고, MongoDB의 Task/Outbox가 고아 객체가 된다. task_id 컬럼을 추가해서 쌓아두고, 조회할 때 task_id 필터로 걸러라"
>
> **결과**: 전 테이블에 task_id 추가, DELETE ALL 제거, 조회 시 `WHERE task_id = ?`

### 4. "에러를 하나만 잡으면 디버깅이 안 된다"

> **문제**: try/except 하나로 첫 번째 에러만 잡고 나머지 필드 에러는 확인 불가
>
> **판단**: "한 row에 video_id도 틀리고 object_class도 틀린데 첫 에러만 보여주면 디버깅이 안 된다. 전부 수집해서 에러별로 각각 Rejection을 만들어라"
>
> **결과**: Refiner에서 필드별로 검증하고 에러를 리스트로 수집. 한 row에서 에러 3개면 Rejection 3건.

### 5. "Summary 집계는 Refiner가 할 일이 아니다"

> **문제**: AI가 RejectionCollector + RejectionSummary + RejectionSample 3개 클래스를 만들어서 Refiner에서 집계하려 함
>
> **판단**: "Refiner는 정제만 해. 집계는 나중에 별도 배치 스케줄러에서 하는 거지, 지금 정제하는 놈이 할 일이 아니다"
>
> **결과**: RejectionCollector/Summary/Sample 전부 삭제. Rejection을 있는 그대로 저장.

### 6. "raw_data를 Rejection에 왜 또 넣어"

> **문제**: Rejection마다 원본 JSON 문자열을 raw_data 필드에 중복 저장
>
> **판단**: "원본은 MongoDB raw_data 컬렉션에 이미 있다. Rejection에 또 넣으면 같은 에러 10만 건이면 같은 JSON이 10만 번 저장된다. source_id로 추적하면 된다"
>
> **결과**: Rejection에서 raw_data 제거. source_id + field로 원본 row 추적.

### 7. "Outbox에 좀비 복구가 없다"

> **문제**: Outbox 메시지가 PENDING → dispatch → mark_published 사이에 프로세스가 죽으면 영원히 재발행 안 됨
>
> **판단**: "스프링에서는 스케줄러가 PROCESSING 상태인데 5분 넘은 놈을 잡는다. 여기도 필요하다"
>
> **결과**: OutboxStatus에 PROCESSING 추가, 좀비 복구 스케줄러(1분 간격) 구현. 재시도 가능하면 PENDING으로 복구, 초과 시 FAILED.

### 8. "파이썬 컨벤션에 맞춰라"

> **문제**: Java/Spring 경험 기반으로 CommandManager/ReadManager, UseCase ABC + Impl, Properties 객체 등 Java 패턴을 적용하려 함
>
> **판단**: AI에게 "파이썬에서도 보통 이렇게 하냐?" 물어봄 → "파이썬 커뮤니티는 보일러플레이트를 극도로 싫어한다. 서비스가 Port를 직접 쓰는 게 정석" 확인
>
> **결과**: Java 패턴 미적용. 서비스 → Port 직접 사용. README에 "Spring에서의 경험을 파이썬 생태계에 맞게 변환했다"고 기술.

---

## 에이전트 시스템

역할별 전문 에이전트와 레이어별 하네스 스킬을 구성하여, 코드 생성과 리뷰를 분리하고 컨벤션 준수를 자동 검증했습니다.

### 핵심 에이전트

| 에이전트 | 역할 |
|---|---|
| `code-reviewer` | 전 레이어 설계 적절성 리뷰 |
| `domain-builder` | 도메인 모델 코드 생성 |
| `service-builder` | Application 레이어 코드 생성 |
| `persistence-builder` | MySQL/MongoDB 어댑터 코드 생성 |
| `unit-test-designer` | 도메인/Application 단위 테스트 설계 |
| `integration-test-designer` | testcontainers 기반 통합 테스트 설계 |

### 하네스 파이프라인

각 레이어마다 하네스가 빌드 → 린트 → 리뷰 → 수정 → 테스트를 자동 순환합니다.

```
[빌드] builder가 코드 생성
  → [리뷰] reviewer가 컨벤션/구조 검증 → PASS or FIX-REQUEST
  → [수정] FIX 시 builder가 수정 (최대 2회)
  → [테스트] test-designer가 테스트 작성 → 실행
```

### 병렬 위임

테스트와 문서 작성은 **다른 세션에서 병렬로 실행**했습니다:
- 세션 A: Domain 단위 테스트 (56개)
- 세션 B: Application 단위 테스트 (81개)
- 세션 C: Adapter 단위 테스트 (46개)
- 세션 D: 통합 E2E 테스트 (21개)
- 세션 E: docs/architecture.md 작성
- 세션 F: docs/data-model.md 작성

---

## AI에게 위임하지 않은 것

- **아키텍처 결정**: DDD + Hexagonal, Polyglot Persistence, Outbox 패턴 등 모든 아키텍처 선택은 직접 판단
- **데이터 분석 해석**: Jupyter Notebook에서 노이즈 패턴을 직접 관찰하고 정제 전략 결정
- **코드 리뷰 판단**: AI가 생성한 코드의 문제점을 직접 지적하고 리팩토링 방향 결정
- **트레이드오프 판단**: "이 과제에서 이 수준이면 충분한가"의 판단 (UoW 미채택, UseCase ABC 미채택 등)

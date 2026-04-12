# ADR-001: Polyglot Persistence (MongoDB + MySQL + Redis)

## 상태

채택 (Accepted)

## 맥락

파이프라인 서버는 세 가지 서로 다른 데이터 특성을 동시에 다룬다:

1. **원본 데이터 보관** — V1/V2 스키마가 혼재된 JSON/CSV 원본을 변환 없이 저장해야 한다
2. **정제 데이터 검색** — 날씨 + 객체 + 신뢰도 등 복합 조건으로 ML 엔지니어가 검색한다
3. **비동기 작업 관리** — 파이프라인 상태 추적, Outbox 이벤트 발행을 트랜잭션으로 묶어야 한다

## 검토한 대안

### 대안 A: MySQL 단일 DB

| 장점 | 단점 |
|------|------|
| 운영 복잡도 최소 | 원본 JSON을 TEXT 컬럼에 넣으면 스키마 변경이 어려움 |
| 트랜잭션 간단 | 작업 상태가 빈번히 갱신되는데 행 락 경합 발생 가능 |
| | Outbox 폴링 시 SELECT FOR UPDATE가 정제 쿼리와 경합 |

### 대안 B: MongoDB + MySQL (채택)

| 장점 | 단점 |
|------|------|
| 원본은 스키마리스 저장 (스키마 변형 대응) | DB 2개 운영 |
| 정제 데이터는 정규화 스키마 + 복합 인덱스 | 크로스 DB 트랜잭션 불가 → 보상 패턴 필요 |
| 작업 상태 갱신이 메인 검색 DB에 영향 없음 | |
| MongoDB Replica Set 트랜잭션으로 Task+Outbox 원자적 저장 | |

## 결정

**대안 B (MongoDB + MySQL + Redis)** 채택.

- **MongoDB**: 원본 보관(스키마리스), 작업 상태(빈번한 갱신), Outbox(트랜잭션)
- **MySQL**: 정제 데이터 저장 + 복합 조건 검색(JOIN, 커버링 인덱스)
- **Redis**: Celery 메시지 브로커 (인메모리 큐)

## 근거

1. **쓰기와 읽기의 특성이 다르다** — 원본 저장은 스키마 유연성이, 검색은 정규화가 각각 더 중요하다. 하나의 DB로 양쪽을 만족시키면 어느 쪽도 최적이 아니다.
2. **작업 상태 갱신이 검색에 영향을 주지 않는다** — MongoDB에서 Phase별 진행률을 갱신하는 것은 MySQL의 검색 쿼리와 완전히 분리된다.
3. **크로스 DB 일관성은 보상 패턴으로 해결한다** — Resume 보상(last_completed_phase) + INSERT IGNORE 멱등성으로 MongoDB→MySQL 간 일관성을 보장한다.

## 결과

- `Domain Port`가 저장소를 추상화하므로, Application 레이어는 어떤 DB를 쓰는지 모른다
- 테스트에서 testcontainers로 MySQL + MongoDB + Redis 3개를 자동 관리한다
- DB 수가 늘어난 만큼 Docker Compose 구성이 복잡해졌지만, 각 DB가 자신의 강점에만 집중한다

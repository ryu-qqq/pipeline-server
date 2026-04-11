# ADR-002: Celery + Transactional Outbox 비동기 처리

## 상태

채택 (Accepted)

## 맥락

51만 건의 데이터를 정제하는 작업은 수십 초가 걸린다. HTTP 요청 안에서 동기로 처리하면 클라이언트가 타임아웃된다. 비동기 처리가 필수이며, 두 가지 문제를 동시에 풀어야 한다:

1. **이벤트 유실 방지** — "Task는 생성됐지만 Worker에게 전달되지 않는" 상황을 막아야 한다
2. **실패 복구** — 파이프라인 중간에 실패하면 처음부터 재실행하지 않고 이어서 재개해야 한다

## 검토한 대안

### 대안 A: FastAPI BackgroundTasks

| 장점 | 단점 |
|------|------|
| 추가 인프라 없음 | 서버 재시작 시 실행 중인 작업 유실 |
| 설정 단순 | 재시도 메커니즘 없음 |
| | 수평 확장 불가 (단일 프로세스) |

### 대안 B: Celery 직접 호출 (send_task)

| 장점 | 단점 |
|------|------|
| 분산 처리 가능 | Task 생성과 Celery 발행이 원자적이지 않음 |
| 재시도/모니터링 내장 | MongoDB 저장 성공 후 Redis 발행 실패 시 이벤트 유실 |

### 대안 C: Celery + Transactional Outbox (채택)

| 장점 | 단점 |
|------|------|
| Task + Outbox를 MongoDB 트랜잭션으로 원자적 저장 | Beat 폴링 지연 (최대 5초) |
| 이벤트 유실 원천 차단 | Outbox 상태 관리 복잡도 증가 |
| 좀비 메시지 자동 복구 | |
| 프로덕션에서 CDC로 전환 시 Application 코드 변경 없음 | |

## 결정

**대안 C (Celery + Transactional Outbox)** 채택.

## 동작 흐름

```
1. POST /analyze
   → MongoDB 트랜잭션: Task(PENDING) + OutboxMessage(PENDING) 원자적 저장

2. Celery Beat (5초 간격)
   → OutboxRelayService.relay()
   → PENDING → PROCESSING → dispatch(task_id) → PUBLISHED

3. Celery Worker
   → pipeline.process_analysis(task_id) 실행
   → Phase별 체크포인트 저장 (resume 포인트)

4. Celery Beat (60초 간격)
   → recover_zombies()
   → 5분 이상 PROCESSING 상태인 메시지 → PENDING 복구 또는 FAILED
```

## 근거

1. **원자성이 핵심이다** — Task와 이벤트를 같은 트랜잭션에 넣지 않으면, "Task는 있는데 실행이 안 되는" 유령 작업이 생긴다. Outbox 패턴이 이를 원천 차단한다.
2. **5초 폴링 지연은 허용 가능하다** — 과제 환경에서 실시간성이 필수가 아니다. 프로덕션에서는 MongoDB Change Stream(CDC)으로 전환하면 지연이 거의 없어진다.
3. **Resume 보상이 Celery 재시도와 결합된다** — Celery의 `max_retries=1`과 Phase별 체크포인트가 합쳐져, 실패 후 완료된 단계를 건너뛰고 재개한다.

## 결과

- `OutboxMessage`는 도메인 모델로, 상태 전이 로직(PENDING→PROCESSING→PUBLISHED)을 자체적으로 관리한다
- Celery Worker 설정: `prefetch_multiplier=1`, `acks_late=True`로 장시간 태스크에 최적화
- 프로덕션 전환 시 Adapter-In(Beat → CDC)만 교체하면 되며, Application/Domain 코드는 그대로 유지된다

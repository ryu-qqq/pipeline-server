# ADR-003: DDD + Hexagonal Architecture 적용

## 상태

채택 (Accepted)

## 맥락

과제 요구사항은 단순해 보이지만(파일 3개 읽어서 DB에 넣기), 실제 구현에서 네 가지 복잡성이 동시에 발생한다:

1. V1/V2 스키마 혼재, 온도 단위 불일치, Enum 검증 등 **정제 규칙이 복잡하다**
2. MongoDB + MySQL + Redis **3개 저장소를 동시에 사용한다**
3. REST API + Celery Worker **두 가지 진입점이 있다**
4. 51만 건을 비동기로 처리하며 **실패 복구(resume)**가 필요하다

## 검토한 대안

### 대안 A: 단순 레이어드 (Controller → Service → Repository)

| 장점 | 단점 |
|------|------|
| 빠르게 구현 가능 | Service가 SQLAlchemy/PyMongo에 직접 의존 |
| 학습 곡선 낮음 | 저장소 교체 시 Service 코드 전체 수정 |
| | 정제 규칙이 Service에 섞여 테스트 어려움 |
| | REST와 Worker가 같은 Service를 쓰려면 DI 구조가 필요 |

### 대안 B: DDD + Hexagonal (채택)

| 장점 | 단점 |
|------|------|
| 정제 규칙이 Domain에 격리 → 순수 Python 테스트 | 초기 파일/클래스 수가 많음 |
| Port 추상화로 저장소 교체 투명 | 패턴 학습 비용 |
| REST/Worker 두 진입점이 Application을 공유 | |
| Domain 테스트가 0.02초 (외부 의존 없음) | |

## 결정

**대안 B (DDD + Hexagonal)** 채택.

## 레이어별 역할과 제약

| 레이어 | 역할 | 의존 제약 |
|--------|------|-----------|
| **Domain** | 모델, VO, Enum, 예외, Port(ABC) | 표준 라이브러리만 (외부 import 금지) |
| **Application** | 서비스, Refiner, PhaseRunner | Domain Port만 의존 (구현체 모름) |
| **Inbound Adapter** | REST Router, Celery Task | Application 호출 |
| **Outbound Adapter** | MySQL, MongoDB, Redis 구현체 | Domain Port 구현 |

```
의존성 방향:  Inbound → Application → Domain ← Outbound
```

## 근거

1. **정제 규칙을 격리해야 테스트가 빠르다** — V1/V2 스키마 감지, 화씨→섭씨 변환, Enum 검증 등이 Domain에 있으면 DB 없이 밀리초 단위로 테스트할 수 있다. 실제로 Domain 테스트 88개가 0.02초에 완료된다.
2. **저장소 3개를 Port로 가려야 한다** — Application이 PyMongo나 SQLAlchemy를 직접 호출하면, 저장소 변경 시 비즈니스 로직까지 수정해야 한다. Port 추상화로 구현체를 교체해도 Application 코드는 변하지 않는다.
3. **두 진입점이 Application을 공유한다** — REST와 Worker가 같은 `PipelineService`, `AnalysisService`를 호출한다. DI 조립만 다르고(`rest_dependencies.py` vs `worker_dependencies.py`) 비즈니스 로직은 동일하다.
4. **과제지만 확장 가능성을 보여줘야 한다** — 평가 기준에 "확장성 있는 코드"가 있다. Hexagonal은 새 Phase 추가(PhaseRunner 구현 + Provider 등록), 저장소 교체(Port 구현체 추가), 진입점 추가(gRPC Adapter 등)가 기존 코드 변경 없이 가능함을 구조적으로 보장한다.

## 결과

- `app/domain/`은 외부 라이브러리를 import하지 않는다 (ruff로 검증 가능)
- 테스트 피라미드: Domain(0.02s) > Application(0.09s) > Adapter(7s) > E2E(13분)
- 파일 수는 많지만, 각 파일의 책임이 명확하고 의존 방향이 단방향이다

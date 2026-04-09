---
name: infra-harness
description: |
  인프라(Redis, Celery, REST, Docker, DI) 레이어 전용 하네스. 빌드 → 린트 → 리뷰 → 수정 → 테스트 파이프라인을 강제 실행한다.
  "인프라 하네스", "infra harness", "라우터 빌드", "REST 빌드", "API 빌드",
  "Redis 빌드", "캐시 빌드", "Celery 빌드", "워커 빌드", "DI 빌드",
  "Docker 빌드", "라우터 검증", "API 리뷰" 등의 요청에 사용한다.
  REST/Worker/Redis/Celery/DI/Docker 코드를 만들거나 검증할 때 이 하네스를 통해 실행한다.
---

# 인프라 하네스

## 개요

인프라 레이어(REST, Worker, Redis, Celery, DI, Docker)의 코드 품질을 **파이프라인으로 강제**하는 실행 하네스.
시스템 경계의 진입점과 인프라 어댑터를 빠짐없이 검증한다.

**핵심 검증 포인트**: Thin Router, DI 체인 정합성, 캐시 전략, Worker 안정성, Docker 구성.

---

## 실행 모드

### 모드 1: 빌드 (`/infra-harness build {대상}`)

예시:
```
/infra-harness build
/infra-harness build rest
/infra-harness build redis
/infra-harness build celery
/infra-harness build docker
/infra-harness build di
```

### 모드 2: 리뷰 (`/infra-harness review {대상}`)

예시:
```
/infra-harness review
/infra-harness review rest
/infra-harness review di
```

### 모드 3: 테스트 (`/infra-harness test {대상}`)

예시:
```
/infra-harness test
/infra-harness test rest
```

---

## 파이프라인 Phase

### build 모드 (전체 실행)

```
[Phase 0] 전제조건 확인
  → docs/convention-python-ddd.md 존재
  → app/domain/ports.py 존재 (TaskDispatcher, CacheRepository ABC)
  → app/application/ 존재 (서비스 인터페이스)
  → docs/design-architecture.md 존재 (API 설계, Docker 구성)

[Phase 1] infra-builder 실행 (코드 생성)
  → inbound/rest/: routers.py, schemas.py, mappers.py
  → inbound/worker/: pipeline_task.py
  → outbound/redis/: client.py, repositories.py, serializer.py
  → outbound/celery/: dispatcher.py
  → dependencies.py, main.py, worker.py
  → docker-compose.yml, Dockerfile

[Phase 2] Ruff 린트 실행
  → ruff check app/adapter/inbound/ app/adapter/outbound/redis/ app/adapter/outbound/celery/
  → ruff check app/dependencies.py app/main.py app/worker.py

[Phase 3] code-reviewer + convention-guardian 병렬 실행
  → code-reviewer:
    - REST: Thin Router(10줄 이하), HTTP 상태 코드, RFC 7807 에러
    - Redis: 캐시 전략(TTL, 무효화), 키 설계, 직렬화
    - Celery: Worker 안정성, 재시도 전략, DI 조립
    - DI: ABC 반환, 세션 관리(yield+commit/rollback/close)
    - Docker: 서비스 구성, depends_on, 환경변수
  → convention-guardian: ADP-IN-001~002, DI-001, FBD-003 검증

[Phase 4] FIX 루프 (최대 2회)
  → infra-builder: FIX-REQUEST 수정
  → Ruff 재실행
  → 재검증 (실패 항목만)

[Phase 5] integration-test-designer 실행
  → tests/adapter/test_routers.py (API 통합 테스트)
  → tests/adapter/test_schemas.py (Pydantic 직렬화 테스트)
  → tests/adapter/test_redis_repositories.py (캐시 테스트)
  → pytest tests/adapter/ -v

[Phase 6] 테스트 FIX 루프 (최대 2회)
  → 실패 테스트 기반 infra-builder 수정
  → 테스트 재실행

[Phase 7] Docker 검증 (build 모드에서만)
  → docker-compose config (설정 유효성)

[완료] 결과 보고
```

---

## 사용자 인터랙션

### 정상 흐름
```
사용자: /infra-harness build

스킬: "인프라 빌드 파이프라인을 시작합니다."

[Phase 1] infra-builder 실행
  → REST 라우터 4개 엔드포인트, Pydantic 스키마, Mapper
  → Celery Worker 태스크, Redis Cache, DI 체인
  → Docker Compose (5개 서비스)

[Phase 2] Ruff 린트
  → ruff check: ✅

[Phase 3] code-reviewer + convention-guardian 병렬 실행
  → code-reviewer: 종합 B등급
    - REST 라우터: A (변환+위임만, 10줄 이하)
    - Redis 캐시: B (무효화 타이밍 확인 필요)
    - Celery: A (재시도 전략 있음)
    - DI 체인: A (ABC 반환, 세션 관리 적절)
  → convention-guardian: ADP-IN PASS, DI PASS, FBD-003 PASS

[Phase 4] FIX 루프 — Round 1/2
  → code-reviewer FIX-REQUEST 1건: 캐시 무효화를 PipelineService 완료 시점에 추가
  → 수정 → 재검증: PASS ✅

[Phase 5] integration-test-designer 실행
  → API 테스트 8개 + 스키마 테스트 4개 + 캐시 테스트 3개
  → pytest: 15/15 통과 ✅

[Phase 7] Docker 검증
  → docker-compose config: ✅

"인프라 빌드 파이프라인 완료. 전체 통과."
```

---

## 에이전트 호출 정보

```
Phase 1 — infra-builder:
  모드: {build}
  대상 경로: app/adapter/inbound/, app/adapter/outbound/redis/,
            app/adapter/outbound/celery/, app/dependencies.py, app/main.py, app/worker.py
  컨벤션: docs/convention-python-ddd.md (ADP-IN, DI 규칙)
  아키텍처: docs/design-architecture.md (API 설계, Docker, Redis)
  서비스: app/application/ (라우터에서 호출할 대상)

Phase 3 — code-reviewer:
  리뷰 범위: inbound + redis + celery + DI + Docker
  관점: Thin Router, 캐시 전략, Worker 안정성, DI 정합성

Phase 3 — convention-guardian:
  검증 범위: adapter/inbound/, dependencies.py
  규칙: ADP-IN-001~002, DI-001, FBD-003

Phase 5 — integration-test-designer:
  대상: REST API + Redis Cache
  테스트 경로: tests/adapter/
  전략: TST-004 (TestClient + DI 오버라이드)
```

---

## FIX 한도

| 단계 | 최대 FIX 횟수 |
|---|---|
| 리뷰 FIX 루프 (Phase 4) | 2회 |
| 테스트 FIX 루프 (Phase 6) | 2회 |

---
name: persistence-harness
description: |
  영속성(MySQL + MongoDB) 레이어 전용 하네스. 빌드 → 린트 → 리뷰 → 수정 → 테스트 파이프라인을 강제 실행한다.
  "영속성 하네스", "persistence harness", "DB 빌드", "Repository 빌드",
  "Entity 빌드", "MongoDB 빌드", "MySQL 빌드", "Mapper 검증",
  "쿼리 리뷰", "인덱스 검증" 등의 요청에 사용한다.
  MySQL/MongoDB 어댑터 코드를 만들거나 검증할 때 반드시 이 하네스를 통해 실행한다.
---

# 영속성 하네스

## 개요

영속성 레이어(MySQL + MongoDB)의 코드 품질을 **파이프라인으로 강제**하는 실행 하네스.
Entity, Document, Repository, Mapper, QueryBuilder를 빠짐없이 검증한다.

**핵심 검증 포인트**: Port(ABC) 충실 구현, Entity/Mapper 분리, 쿼리 성능, 인덱스 설계, 벌크 연산.

---

## 실행 모드

### 모드 1: 빌드 (`/persistence-harness build {대상}`)

예시:
```
/persistence-harness build
/persistence-harness build mysql
/persistence-harness build mongodb
/persistence-harness build query_builder
```

### 모드 2: 리뷰 (`/persistence-harness review {대상}`)

예시:
```
/persistence-harness review
/persistence-harness review mysql
/persistence-harness review mongodb
```

### 모드 3: 테스트 (`/persistence-harness test {대상}`)

예시:
```
/persistence-harness test
/persistence-harness test mysql
```

---

## 파이프라인 Phase

### build 모드 (전체 실행)

```
[Phase 0] 전제조건 확인
  → docs/convention-python-ddd.md 존재
  → app/domain/ports.py 존재 (구현할 ABC 목록)
  → docs/design-architecture.md 존재 (인덱스 설계, Polyglot 구조)

[Phase 1] persistence-builder 실행 (코드 생성)
  → mysql/: database.py, entities.py, repositories.py, mappers.py, query_builder.py
  → mongodb/: client.py, documents.py, repositories.py, mappers.py

[Phase 2] Ruff 린트 실행
  → ruff check app/adapter/outbound/mysql/ app/adapter/outbound/mongodb/
  → ruff format --check ...

[Phase 3] code-reviewer + convention-guardian 병렬 실행
  → code-reviewer:
    - MySQL: 쿼리 성능, N+1 탐지, 인덱스 활용, 벌크 연산, SQL Injection 방지
    - MongoDB: 스키마 설계, 인덱스, 벌크 insert, 청크 분할
    - 공통: Mapper 정확성, Port 계약 충실 구현
  → convention-guardian: ADP-OUT-001~003, FBD-004 검증

[Phase 4] FIX 루프 (최대 2회)
  → persistence-builder: FIX-REQUEST 수정
  → Ruff 재실행
  → 재검증 (실패 항목만)

[Phase 5] integration-test-designer 실행
  → tests/adapter/test_mysql_repositories.py 작성
  → tests/adapter/test_mongodb_repositories.py 작성
  → pytest tests/adapter/test_mysql_repositories.py tests/adapter/test_mongodb_repositories.py -v

[Phase 6] 테스트 FIX 루프 (최대 2회)
  → 실패 테스트 기반 persistence-builder 수정
  → 테스트 재실행

[완료] 결과 보고
```

---

## 사용자 인터랙션

### 정상 흐름
```
사용자: /persistence-harness build

스킬: "영속성 빌드 파이프라인을 시작합니다."

[Phase 1] persistence-builder 실행
  → MySQL: entities.py(4개 Entity), repositories.py(5개 Repo), mappers.py, query_builder.py
  → MongoDB: documents.py(2개 Document), repositories.py(2개 Repo), mappers.py

[Phase 2] Ruff 린트
  → ruff check: ✅

[Phase 3] code-reviewer + convention-guardian 병렬 실행
  → code-reviewer: 종합 B등급
    - MySQL 쿼리: A (벌크 연산 사용, 파라미터 바인딩)
    - MySQL 인덱스: B (odd_tags 복합 인덱스 순서 확인 필요)
    - MongoDB: A (insert_many, 인덱스 설정)
    - Mapper: A (양방향 변환 정확)
  → convention-guardian: ADP-OUT PASS, FBD-004 PASS (relationship 없음)

[Phase 4] FIX 루프 — Round 1/2
  → code-reviewer FIX-REQUEST 1건: 복합 인덱스 순서 조정
  → 수정 → 재검증: PASS ✅

[Phase 5] integration-test-designer 실행
  → MySQL 테스트 12개 + MongoDB 테스트 6개 작성
  → pytest: 18/18 통과 ✅

"영속성 빌드 파이프라인 완료. 전체 통과."
```

---

## 에이전트 호출 정보

```
Phase 1 — persistence-builder:
  모드: {build}
  대상 경로: app/adapter/outbound/mysql/, app/adapter/outbound/mongodb/
  컨벤션: docs/convention-python-ddd.md (ADP-OUT 규칙)
  Port 정의: app/domain/ports.py
  아키텍처: docs/design-architecture.md (인덱스 설계, Polyglot)

Phase 3 — code-reviewer:
  리뷰 범위: app/adapter/outbound/mysql/, app/adapter/outbound/mongodb/
  관점: 쿼리 성능, 인덱스, 벌크 연산, Mapper 정확성, N+1

Phase 3 — convention-guardian:
  검증 범위: app/adapter/outbound/mysql/, app/adapter/outbound/mongodb/
  규칙: ADP-OUT-001~003, FBD-004

Phase 5 — integration-test-designer:
  대상: app/adapter/outbound/mysql/, app/adapter/outbound/mongodb/
  테스트 경로: tests/adapter/
  전략: TST-004 (SQLite in-memory)
```

---

## FIX 한도

| 단계 | 최대 FIX 횟수 |
|---|---|
| 리뷰 FIX 루프 (Phase 4) | 2회 |
| 테스트 FIX 루프 (Phase 6) | 2회 |

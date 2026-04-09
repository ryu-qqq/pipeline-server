---
name: service-harness
description: |
  Application 레이어 전용 하네스. 빌드 → 린트 → 리뷰 → 수정 → 테스트 파이프라인을 강제 실행한다.
  "서비스 하네스", "서비스 파이프라인", "service harness", "서비스 빌드",
  "서비스 리뷰 돌려줘", "application 검증", "UseCase 빌드", "파서 검증",
  "검증기 빌드", "서비스 수정 검증" 등의 요청에 사용한다.
  Application 코드를 만들거나, 기존 코드를 검증할 때 반드시 이 하네스를 통해 실행한다.
---

# 서비스 하네스

## 개요

Application 레이어의 코드 품질을 **파이프라인으로 강제**하는 실행 하네스.
"만든다 → 린트한다 → 리뷰한다 → 고친다 → 테스트한다"를 빠짐없이 수행한다.

**핵심 검증 포인트**: 서비스가 Port(ABC)만 의존하는지, 트랜잭션 경계가 적절한지, CQRS 분리가 되어있는지.

---

## 실행 모드

### 모드 1: 빌드 (`/service-harness build {대상}`)
신규 서비스 코드를 생성하고 전체 파이프라인을 돌린다.

예시:
```
/service-harness build
/service-harness build analysis_service
/service-harness build parsers
/service-harness build validators
```

### 모드 2: 리뷰 (`/service-harness review {대상}`)
기존 서비스 코드를 리뷰하고, FIX가 필요하면 수정 루프를 돌린다.

예시:
```
/service-harness review
/service-harness review pipeline_service
```

### 모드 3: 테스트 (`/service-harness test {대상}`)
서비스 테스트만 작성/실행한다.

예시:
```
/service-harness test
/service-harness test parsers
```

---

## 파이프라인 Phase

### build 모드 (전체 실행)

```
[Phase 0] 전제조건 확인
  → docs/convention-python-ddd.md 존재
  → app/domain/ 코드 존재 (서비스가 의존하는 Port/Model)
  → app/application/ 디렉토리 존재

[Phase 1] service-builder 실행 (코드 생성)
  → analysis_service.py, pipeline_service.py, task_service.py,
    search_service.py, rejection_service.py, parsers.py, validators.py

[Phase 2] Ruff 린트 실행
  → ruff check app/application/
  → ruff format --check app/application/

[Phase 3] code-reviewer + convention-guardian 병렬 실행
  → code-reviewer: 트랜잭션 경계, CQRS 분리, 서비스 책임, Port 사용 리뷰
  → convention-guardian: APP-001~004, FBD-002 검증

[Phase 4] FIX 루프 (최대 2회)
  → service-builder: FIX-REQUEST 수정
  → Ruff 재실행
  → 재검증 (실패 항목만)

[Phase 5] unit-test-designer 실행
  → tests/application/ 테스트 작성
  → pytest tests/application/ -v 실행

[Phase 6] 테스트 FIX 루프 (최대 2회)
  → 실패 테스트 기반 service-builder 수정
  → 테스트 재실행

[완료] 결과 보고
```

---

## 사용자 인터랙션

### 정상 흐름
```
사용자: /service-harness build

스킬: "서비스 빌드 파이프라인을 시작합니다."

[Phase 1] service-builder 실행
  → 5개 서비스 + parsers.py + validators.py 생성

[Phase 2] Ruff 린트
  → ruff check: ✅

[Phase 3] code-reviewer + convention-guardian 병렬 실행
  → code-reviewer: 종합 B등급
    - 트랜잭션 경계: A
    - CQRS 분리: A (Command/Query 서비스 분리됨)
    - 서비스 책임: B (PipelineService가 Port 5개 의존 — 경고)
    - Port 사용: A
  → convention-guardian: APP 규칙 전체 PASS

[Phase 4] FIX 루프 — Round 1/2
  → code-reviewer FIX-REQUEST 1건: PipelineService 분할 제안
  → service-builder 수정: 정제 Phase별 내부 메서드 분리
  → 재검증: PASS ✅

[Phase 5] unit-test-designer 실행
  → 테스트 22개 작성
  → pytest: 22/22 통과 ✅

"서비스 빌드 파이프라인 완료. 전체 통과."
```

### ESCALATION 발생 시
```
[Phase 4] FIX 루프 — Round 2/2 (최대 도달)
  → 여전히 FAIL 1건

스킬: "FIX 루프 2회를 소진했습니다. 미해결 이슈:"
      1. SearchService에서 CacheRepository.get() 반환값을 도메인 모델로 역직렬화하는 로직이
         application에 있어야 하는지, adapter에 있어야 하는지

      "어떻게 하시겠습니까?"
      A) CacheRepository의 Port 시그니처를 도메인 모델 반환으로 변경
      B) application에서 dict → 도메인 모델 변환 유지
      C) 직접 방향을 지정

사용자: A로 가자

스킬: → service-builder + domain-builder에 결정 전달 → 수정 → 재검증
```

---

## 에이전트 호출 정보

```
Phase 1 — service-builder:
  모드: {build}
  대상 경로: app/application/
  컨벤션: docs/convention-python-ddd.md (APP 규칙)
  도메인 코드: app/domain/ (Port, Model 참조)
  아키텍처: docs/design-architecture.md (CQRS, Write/Read Path)

Phase 3 — code-reviewer:
  리뷰 범위: app/application/
  관점: 트랜잭션 경계, CQRS 분리, 서비스 책임, Port 사용

Phase 3 — convention-guardian:
  검증 범위: app/application/
  규칙: APP-001~004, FBD-002

Phase 5 — unit-test-designer:
  대상: app/application/
  테스트 경로: tests/application/
  전략: TST-003 (Mock Repository)
```

---

## FIX 한도

| 단계 | 최대 FIX 횟수 |
|---|---|
| 리뷰 FIX 루프 (Phase 4) | 2회 |
| 테스트 FIX 루프 (Phase 6) | 2회 |

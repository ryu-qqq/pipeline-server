---
name: domain-harness
description: |
  도메인 레이어 전용 하네스. 빌드 → 린트 → 리뷰 → 수정 → 테스트 파이프라인을 강제 실행한다.
  "도메인 하네스", "도메인 파이프라인", "domain harness", "도메인 빌드",
  "도메인 리뷰 돌려줘", "도메인 검증", "도메인 수정 검증", "VO 빌드", "모델 검증" 등의 요청에 사용한다.
  도메인 코드를 만들거나, 기존 도메인 코드를 검증할 때 반드시 이 하네스를 통해 실행한다.
---

# 도메인 하네스

## 개요

도메인 레이어의 코드 품질을 **파이프라인으로 강제**하는 실행 하네스.
"만든다 → 린트한다 → 리뷰한다 → 고친다 → 테스트한다"를 빠짐없이 수행하고, 각 단계의 결과를 다음 단계에 전달한다.

**문제**: builder에게 코드 생성을 시키고 리뷰/테스트 없이 바로 커밋하면 품질이 보장되지 않는다.
**해결**: 이 하네스가 전체 흐름을 오케스트레이션하여 리뷰와 테스트를 건너뛸 수 없게 한다.

---

## 실행 모드

### 모드 1: 빌드 (`/domain-harness build`)
신규 도메인 코드를 생성하고 전체 파이프라인을 돌린다.

예시:
```
/domain-harness build
/domain-harness build models
/domain-harness build value_objects
```

### 모드 2: 리뷰 (`/domain-harness review`)
기존 도메인 코드를 리뷰하고, FIX가 필요하면 수정 루프를 돌린다.

예시:
```
/domain-harness review
/domain-harness review ports
```

### 모드 3: 테스트 (`/domain-harness test`)
도메인 테스트만 작성/실행한다 (코드는 이미 있다고 가정).

예시:
```
/domain-harness test
/domain-harness test value_objects
```

---

## 실행 시 이 스킬이 하는 것

1. 사용자 커맨드를 파싱한다 (모드 + 대상)
2. 해당 모드에 맞는 에이전트를 순차 호출한다
3. 에이전트가 반환하는 중간 결과를 사용자에게 보고한다
4. ESCALATION이 발생하면 사용자에게 선택지를 제시한다
5. 최종 결과를 요약하여 보고한다

---

## 파이프라인 Phase

### build 모드 (전체 실행)

```
[Phase 0] 전제조건 확인
  → docs/convention-python-ddd.md 존재
  → app/domain/ 디렉토리 존재

[Phase 1] domain-builder 실행 (코드 생성)
  → models.py, value_objects.py, enums.py, exceptions.py, ports.py

[Phase 2] Ruff 린트 실행
  → ruff check app/domain/
  → ruff format --check app/domain/

[Phase 3] code-reviewer + convention-guardian 병렬 실행
  → code-reviewer: VO 설계, Rich Domain, 예외 계층, Port 설계 리뷰
  → convention-guardian: DOM-001~006, FBD-001/005/006 검증

[Phase 4] FIX 루프 (최대 3회)
  → domain-builder: FIX-REQUEST 수정
  → Ruff 재실행
  → code-reviewer + convention-guardian 재검증 (실패 항목만)

[Phase 5] unit-test-designer 실행
  → tests/domain/ 테스트 작성
  → pytest tests/domain/ -v 실행

[Phase 6] 테스트 FIX 루프 (최대 2회)
  → 실패 테스트 기반 domain-builder 수정
  → 테스트 재실행

[완료] 결과 보고
```

### review 모드 (Phase 1 건너뜀)
Phase 2부터 실행. 기존 코드를 검증.

### test 모드 (Phase 5부터)
Phase 5~6만 실행. 테스트만 작성/실행.

---

## 사용자 인터랙션

### 정상 흐름
```
사용자: /domain-harness build

스킬: "도메인 빌드 파이프라인을 시작합니다."

[Phase 1] domain-builder 실행
  → models.py, value_objects.py, enums.py, exceptions.py, ports.py 생성
  → 자체 검증: ruff PASS

[Phase 2] Ruff 린트
  → ruff check: ✅ 0 violations
  → ruff format: ✅

[Phase 3] code-reviewer + convention-guardian 병렬 실행
  → code-reviewer: 종합 B등급 (VO 설계 A, Rich Domain B, 예외 계층 A, Port B)
  → convention-guardian: DOM-001~006 전체 PASS, FBD PASS

[Phase 4] FIX 루프 — Round 1/3
  → code-reviewer FIX-REQUEST 2건: VideoId 검증 추가, Port 메서드 네이밍
  → domain-builder 수정
  → 재검증: PASS ✅

[Phase 5] unit-test-designer 실행
  → 테스트 18개 작성
  → pytest: 18/18 통과 ✅

"도메인 빌드 파이프라인 완료. 전체 통과."
```

### ESCALATION 발생 시
```
[Phase 4] FIX 루프 — Round 3/3 (최대 도달)
  → 여전히 FAIL 1건

스킬: "FIX 루프 3회를 소진했습니다. 미해결 이슈:"
      1. Rejection 모델에 raw_data(dict)를 frozen dataclass에서 어떻게 다룰지
         — dict는 mutable이라 frozen=True와 충돌

      "어떻게 하시겠습니까?"
      A) raw_data를 JSON 문자열(str)로 변환하여 저장
      B) raw_data 필드를 tuple[tuple[str, Any], ...]로 변환
      C) 직접 방향을 지정

사용자: A로 가자

스킬: → domain-builder에 결정 전달 → 수정 → 재검증
```

---

## 에이전트 호출 정보

이 스킬이 각 Phase에서 호출하는 에이전트와 전달 정보:

```
Phase 1 — domain-builder:
  모드: {build}
  대상 경로: app/domain/
  컨벤션: docs/convention-python-ddd.md (DOM 규칙)
  레퍼런스: docs/research-python-ddd.md

Phase 2 — Bash:
  ruff check app/domain/
  ruff format --check app/domain/

Phase 3 — code-reviewer:
  리뷰 범위: app/domain/
  관점: VO 설계, Rich Domain, 예외 계층, Port 설계
  컨벤션: docs/convention-python-ddd.md
  레퍼런스: docs/research-python-ddd.md

Phase 3 — convention-guardian:
  검증 범위: app/domain/
  규칙: DOM-001~006, FBD-001/005/006

Phase 5 — unit-test-designer:
  대상: app/domain/
  테스트 경로: tests/domain/
  전략: TST-002 (순수 단위, Mock 없음)
```

---

## FIX 한도

| 단계 | 최대 FIX 횟수 |
|---|---|
| 리뷰 FIX 루프 (Phase 4) | 3회 |
| 테스트 FIX 루프 (Phase 6) | 2회 |

한도 초과 시 → ESCALATION → project-lead 분석 → 사용자에게 선택지 제시

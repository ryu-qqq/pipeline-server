# 데이터 분석 결과

## 1. 파일 개요

| 파일 | 레코드 수 | 크기 | 설명 |
|---|---|---|---|
| `selections.json` | 98,776건 | 18.5MB | 차량 수집 영상 메타데이터 |
| `odds.csv` | 96,799건 | 2.6MB | ODD 태깅 (기상, 시간대, 노면) |
| `labels.csv` | 322,856건 | 16.5MB | 객체 탐지 추론 결과 (영상당 N개) |

---

## 2. selections.json 분석

### 2-1. 스키마 변형 (= "차량마다 수집 소프트웨어 버전이 다름")

**2가지 스키마가 혼재:**

| 스키마 | 건수 | 비율 | 구조 |
|---|---|---|---|
| **sensor 타입** (v2) | 69,088건 | 69.9% | `sensor.temperature.value/unit`, `sensor.wiper.isActive/level`, `sensor.headlights` |
| **flat 타입** (v1) | 29,688건 | 30.1% | `temperature`, `isWiperOn`, `headlightsOn` |

→ **정제 시 두 스키마를 하나의 통합 모델로 정규화해야 함**

### 2-2. 온도 단위 불일치

| 스키마 | 단위 | 범위 |
|---|---|---|
| sensor 타입 | **화씨(F)** | 5°F ~ 113°F |
| flat 타입 | **섭씨(C)** (추정) | -15°C ~ 45°C |

검증: 5°F = -15°C, 113°F = 45°C → **flat 타입은 섭씨, sensor 타입은 화씨. 통일 필요.**

### 2-3. 기타 필드

- **id**: 1 ~ 98,776 (유니크, 중복 없음, 누락 없음)
- **recordedAt**: 전부 존재. ISO 8601 + KST(+09:00)
- **sourcePath**: 전부 존재. `/data/raw/...` 또는 `/data/processed/...` 패턴

### 2-4. 발견된 노이즈: 없음 (스키마 변형 자체가 정제 대상)

---

## 3. odds.csv 분석

### 3-1. 컬럼 및 값 분포

| 컬럼 | 유니크 값 | 분포 |
|---|---|---|
| weather | 4개 | sunny(16,279) / cloudy(55,602) / rainy(19,390) / snowy(5,528) |
| time_of_day | 2개 | day(57,926) / night(38,873) |
| road_surface | 4개 | dry(58,051) / wet(33,175) / snowy(4,740) / icy(833) |

→ **허용값 외의 이상 값은 없음** (깨끗한 enum)

### 3-2. 발견된 노이즈

#### 노이즈 1: video_id 중복 태깅 (20건)
같은 영상에 대해 서로 다른 ODD 태깅이 2건씩 존재.

```
video_id=4938: (cloudy, day, dry) vs (rainy, day, wet)   ← 어느 게 맞는지 판단 불가
video_id=9876: (sunny, day, dry) vs (cloudy, day, wet)
```

→ **사람이 중복 태깅한 것. 동일 video_id에 2건 → 어떤 것을 채택할지 정책 필요**

#### 노이즈 2: video_id 제로패딩 불일치 (30건)
```
odds.csv: video_id = "00012346"
selections.json: id = 12346
```
→ **제로패딩 제거 후 매칭하면 전부 연결됨. 정제 시 정규화 필요.**

#### 노이즈 3: selections에 없는 매칭 불가 video_id
- odds에만 존재 (제로패딩 제거해도 매칭 안 되는 것): **0건** (전부 매칭됨)
- selections에만 존재 (odds 태깅 누락): **2,027건**

---

## 4. labels.csv 분석

### 4-1. 기본 구조

영상 1개당 여러 object_class 행이 존재 (1:N 관계)

| 컬럼 | 설명 | 범위 |
|---|---|---|
| video_id | 영상 ID | 95,054개 유니크 |
| object_class | 객체 종류 | 8종 (car, pedestrian, traffic_sign, traffic_light, truck, bus, cyclist, motorcycle) |
| obj_count | 탐지 개수 | -10 ~ 50 (이상치 포함) |
| avg_confidence | 평균 신뢰도 | 0.55 ~ 0.99 |
| labeled_at | 라벨링 시각 | ISO 8601 |

### 4-2. 발견된 노이즈

#### 노이즈 1: 음수 obj_count (10건)
```
video_id=5888,  class=car, count=-1
video_id=15742, class=car, count=-3
video_id=25645, class=car, count=-2
```
→ **객체 수는 음수가 될 수 없음. 거부 대상.**

#### 노이즈 2: 소수점 obj_count (15건)
```
video_id=1954,  class=car, count=0.1
video_id=8523,  class=car, count=0.2
video_id=15079, class=truck, count=0.3
```
→ **객체 수는 정수여야 함. 거부 대상.**

#### 노이즈 3: obj_count=0 (5,186건)
→ **탐지된 객체가 0개인 레코드. 유효한 데이터일 수 있음 (해당 클래스가 없는 것). 거부는 아니지만 필터링 시 고려.**

#### 노이즈 4: 동일 video_id + object_class 중복 (20건)
```
video_id=4905, class=car: (count=41, conf=0.96) vs (count=5, conf=0.80)
```
→ **같은 영상 같은 클래스에 2번 라벨링. 중복 태깅. 정책 필요.**

#### 노이즈 5: selections에 없는 video_id
- labels에만 존재: **0건** (전부 selections에 존재)
- selections에만 존재 (라벨링 누락): **3,722건**

---

## 5. 세 파일 간 관계 (JOIN)

```
selections (98,776건)
    ├── odds (96,799건) : selection.id = odds.video_id
    │   ├── 매칭됨: 96,769건 (제로패딩 30건 정규화 후)
    │   ├── 중복 태깅: 20건
    │   └── odds에서 selections 못 찾음: 0건
    │
    └── labels (322,856건) : selection.id = labels.video_id
        ├── 매칭됨: 322,856건 (전부)
        ├── 중복 라벨링: 20건
        └── labels에서 selections 못 찾음: 0건

3파일 모두 존재: 95,044건
selections에만 (odds·labels 모두 없음): 2,017건
```

---

## 6. 노이즈 종합 및 거부 정책 (안)

### 6-1. 거부 사유 분류 체계

| 코드 | 거부 사유 | 단계 | 건수 |
|---|---|---|---|
| `DUPLICATE_ODD_TAGGING` | 동일 영상 ODD 중복 태깅 | odd_tagging | 20건 (40행) |
| `DUPLICATE_LABEL` | 동일 영상+클래스 라벨 중복 | auto_labeling | 20건 (40행) |
| `NEGATIVE_OBJ_COUNT` | 객체 수 음수 | auto_labeling | 10건 |
| `FRACTIONAL_OBJ_COUNT` | 객체 수 소수점 | auto_labeling | 15건 |
| `ZERO_PADDED_VIDEO_ID` | video_id 제로패딩 (정규화로 해결) | odd_tagging | 30건 (거부 아님, 정제) |

### 6-2. 정제 항목 (거부가 아닌 변환)

| 항목 | 처리 |
|---|---|
| 스키마 통합 (v1/v2) | 두 스키마를 통합 모델로 정규화 |
| 온도 단위 통일 | 화씨 → 섭씨 변환 (또는 반대) |
| video_id 제로패딩 | 정수로 정규화하여 매칭 |
| odds/labels 누락 | selection만 있고 odds/labels 없는 건 → 부분 데이터로 적재 (거부 아님) |

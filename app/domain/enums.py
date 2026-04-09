from enum import StrEnum


class Weather(StrEnum):
    """기상 조건 (ODD 태깅 항목)"""

    SUNNY = "sunny"
    CLOUDY = "cloudy"
    RAINY = "rainy"
    SNOWY = "snowy"


class TimeOfDay(StrEnum):
    """시간대 (ODD 태깅 항목)"""

    DAY = "day"
    NIGHT = "night"


class RoadSurface(StrEnum):
    """노면 상태 (ODD 태깅 항목)"""

    DRY = "dry"
    WET = "wet"
    SNOWY = "snowy"
    ICY = "icy"


class ObjectClass(StrEnum):
    """객체 클래스 (자동 라벨링 탐지 대상)"""

    CAR = "car"
    PEDESTRIAN = "pedestrian"
    TRAFFIC_SIGN = "traffic_sign"
    TRAFFIC_LIGHT = "traffic_light"
    TRUCK = "truck"
    BUS = "bus"
    CYCLIST = "cyclist"
    MOTORCYCLE = "motorcycle"


class Stage(StrEnum):
    """데이터 파이프라인 단계"""

    SELECTION = "selection"
    ODD_TAGGING = "odd_tagging"
    AUTO_LABELING = "auto_labeling"


class TaskStatus(StrEnum):
    """분석 작업 상태"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FileType(StrEnum):
    """파일 형식"""

    JSON = "json"
    CSV = "csv"


class RejectionReason(StrEnum):
    """거부 사유"""

    DUPLICATE_TAGGING = "duplicate_tagging"
    DUPLICATE_LABEL = "duplicate_label"
    NEGATIVE_OBJ_COUNT = "negative_obj_count"
    FRACTIONAL_OBJ_COUNT = "fractional_obj_count"
    INVALID_FORMAT = "invalid_format"
    UNKNOWN_SCHEMA = "unknown_schema"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_ENUM_VALUE = "invalid_enum_value"
    UNLINKED_RECORD = "unlinked_record"

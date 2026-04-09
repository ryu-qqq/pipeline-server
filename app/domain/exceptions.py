class DomainError(Exception):
    """도메인 규칙 위반 시 발생하는 최상위 예외"""

    error_code: str = "DOMAIN_ERROR"
    message: str = "도메인 규칙 위반"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.__class__.message
        super().__init__(self.message)


# === Selection 관련 예외 ===


class SelectionParseError(DomainError):
    """Selection 파싱 실패 (알 수 없는 스키마, 필수 필드 누락 등)"""

    error_code = "SELECTION_PARSE_ERROR"
    message = "Selection 데이터 파싱에 실패했습니다"


class UnknownSchemaError(SelectionParseError):
    """인식할 수 없는 Selection 스키마 버전"""

    error_code = "UNKNOWN_SCHEMA"
    message = "인식할 수 없는 스키마입니다"


class TemperatureConversionError(SelectionParseError):
    """온도 단위 변환 실패"""

    error_code = "TEMPERATURE_CONVERSION_ERROR"
    message = "온도 변환에 실패했습니다"


# === ODD 태깅 관련 예외 ===


class InvalidOddTagError(DomainError):
    """ODD 태깅 데이터 오류"""

    error_code = "INVALID_ODD_TAG"
    message = "ODD 태깅 데이터가 유효하지 않습니다"


class InvalidEnumValueError(InvalidOddTagError):
    """허용되지 않은 Enum 값"""

    error_code = "INVALID_ENUM_VALUE"
    message = "허용되지 않은 값입니다"


# === Label 관련 예외 ===


class InvalidLabelError(DomainError):
    """Label 데이터 오류"""

    error_code = "INVALID_LABEL"
    message = "Label 데이터가 유효하지 않습니다"


class NegativeCountError(InvalidLabelError):
    """객체 수가 음수"""

    error_code = "NEGATIVE_OBJ_COUNT"
    message = "객체 수는 음수일 수 없습니다"


class FractionalCountError(InvalidLabelError):
    """객체 수가 소수점"""

    error_code = "FRACTIONAL_OBJ_COUNT"
    message = "객체 수는 정수여야 합니다"


# === 공통 예외 ===


class DuplicateRecordError(DomainError):
    """중복 레코드"""

    error_code = "DUPLICATE_RECORD"
    message = "중복된 레코드입니다"


class DataNotFoundError(DomainError):
    """데이터 미존재"""

    error_code = "DATA_NOT_FOUND"
    message = "데이터를 찾을 수 없습니다"


class InvalidFormatError(DomainError):
    """데이터 형식 오류"""

    error_code = "INVALID_FORMAT"
    message = "데이터 형식이 올바르지 않습니다"

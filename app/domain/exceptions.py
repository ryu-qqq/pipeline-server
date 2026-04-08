class DomainError(Exception):
    """도메인 규칙 위반 시 발생하는 예외"""

    def __init__(self, error_code: str, message: str) -> None:
        self.error_code = error_code
        self.message = message
        super().__init__(message)

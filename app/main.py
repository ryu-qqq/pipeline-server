import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.adapter.inbound.routers import router
from app.adapter.inbound.schemas import ProblemDetail
from app.adapter.outbound.mysql.database import create_tables
from app.domain.exceptions import DomainError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Pipeline Server",
    description="자율주행 영상 데이터 정제·분석 파이프라인 API",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    create_tables()
    from app.adapter.outbound.mongodb.client import ensure_indexes

    ensure_indexes()


# === 글로벌 예외 핸들러 (= Spring @RestControllerAdvice) ===


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    """도메인 규칙 위반 (400)"""
    logger.warning("DomainError: code=%s, message=%s, path=%s", exc.error_code, exc.message, request.url.path)
    return JSONResponse(
        status_code=400,
        content=ProblemDetail(
            title="Bad Request",
            status=400,
            detail=exc.message,
            code=exc.error_code,
            instance=str(request.url.path),
        ).model_dump(),
        headers={"x-error-code": exc.error_code},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """요청 파라미터 검증 실패 (422 → 400으로 변환)"""
    errors = {}
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "query")
        errors[field] = error["msg"]

    logger.warning("ValidationError: path=%s, errors=%s", request.url.path, errors)
    return JSONResponse(
        status_code=400,
        content=ProblemDetail(
            title="Validation Failed",
            status=400,
            detail="요청 파라미터 검증에 실패했습니다",
            code="VALIDATION_FAILED",
            instance=str(request.url.path),
            errors=errors,
        ).model_dump(),
        headers={"x-error-code": "VALIDATION_FAILED"},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """값 오류 (400)"""
    logger.warning("ValueError: %s, path=%s", exc, request.url.path)
    return JSONResponse(
        status_code=400,
        content=ProblemDetail(
            title="Bad Request",
            status=400,
            detail=str(exc),
            code="INVALID_VALUE",
            instance=str(request.url.path),
        ).model_dump(),
        headers={"x-error-code": "INVALID_VALUE"},
    )


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """처리되지 않은 예외 (500)"""
    logger.exception("UnhandledException: path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=ProblemDetail(
            title="Internal Server Error",
            status=500,
            detail="서버 내부 오류가 발생했습니다",
            code="INTERNAL_ERROR",
            instance=str(request.url.path),
        ).model_dump(),
        headers={"x-error-code": "INTERNAL_ERROR"},
    )


app.include_router(router)

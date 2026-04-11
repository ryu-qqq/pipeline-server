from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.adapter.inbound.rest.mappers import (
    DataSearchCriteriaMapper,
    RejectionCriteriaMapper,
    RejectionResponseMapper,
    SearchResultResponseMapper,
    TaskResponseMapper,
)
from app.adapter.inbound.rest.schemas import (
    ApiResponse,
    DataSearchRequest,
    PageApiResponse,
    ProblemDetail,
    RejectionResponse,
    RejectionSearchRequest,
    SearchResultResponse,
    TaskResponse,
    TaskSubmitResponse,
)
from app.application.analysis_service import AnalysisService
from app.application.data_read_service import DataReadService
from app.application.rejection_read_service import RejectionReadService
from app.application.task_read_service import TaskReadService
from app.domain.enums import TaskStatus
from app.rest_dependencies import (
    get_analysis_service,
    get_data_read_service,
    get_rejection_read_service,
    get_task_read_service,
)

router = APIRouter(tags=["Pipeline"])


@router.post(
    "/analyze",
    status_code=202,
    response_model=ApiResponse[TaskSubmitResponse],
    summary="데이터 분석 요청",
    description="3개 파일(selections.json, odds.csv, labels.csv)을 읽어 MongoDB에 원본을 적재하고, "
    "비동기 정제 파이프라인을 시작한다. task_id를 반환하며, 진행 상태는 GET /analyze/{task_id}로 조회한다.",
    responses={
        202: {"description": "분석 접수 완료 — 비동기 정제 시작"},
        400: {"model": ProblemDetail, "description": "파일 없음, JSON 파싱 실패 등"},
        409: {"model": ProblemDetail, "description": "이미 진행 중인 분석 작업이 존재"},
        500: {"model": ProblemDetail, "description": "서버 내부 오류"},
    },
)
def analyze(service: AnalysisService = Depends(get_analysis_service)):
    task_id = service.submit()

    return JSONResponse(
        status_code=202,
        content=ApiResponse(
            data=TaskSubmitResponse(task_id=task_id, status=TaskStatus.PENDING),
        ).model_dump(),
    )


@router.get(
    "/analyze/{task_id}",
    response_model=ApiResponse[TaskResponse],
    summary="분석 작업 진행 상태 조회",
    description="task_id에 해당하는 분석 작업의 상태(PENDING/PROCESSING/COMPLETED/FAILED)와 "
    "Phase별 진행률(Selection, ODD Tagging, Auto Labeling)을 조회한다.",
    responses={
        200: {"description": "작업 상태 반환"},
        400: {"model": ProblemDetail, "description": "존재하지 않는 task_id"},
        500: {"model": ProblemDetail, "description": "서버 내부 오류"},
    },
)
def get_task_status(
    task_id: str,
    service: TaskReadService = Depends(get_task_read_service),
):
    task = service.get_task(task_id)
    return ApiResponse(data=TaskResponseMapper.from_domain(task))


@router.get(
    "/rejections",
    response_model=PageApiResponse[RejectionResponse],
    summary="거부 데이터 조회",
    description="정제 과정에서 거부된 데이터를 조회한다. "
    "거부 사유(reason)와 발생 단계(stage)로 필터링할 수 있으며, "
    "source_id로 특정 원본 row의 에러를, field로 특정 필드의 에러만 조회할 수 있다. "
    "페이징은 offset(page) 또는 cursor(after) 방식을 지원한다.",
    responses={
        200: {"description": "거부 데이터 목록 (페이지네이션)"},
        400: {"model": ProblemDetail, "description": "잘못된 파라미터 (page + after 동시 사용 등)"},
        500: {"model": ProblemDetail, "description": "서버 내부 오류"},
    },
)
def get_rejections(
    request: RejectionSearchRequest = Depends(),
    service: RejectionReadService = Depends(get_rejection_read_service),
):
    criteria = RejectionCriteriaMapper.to_domain(request)
    rejections, total = service.search(criteria)
    items = [RejectionResponseMapper.from_domain(r) for r in rejections]

    return PageApiResponse.of(items=items, total=total, page=request.page or 1, size=request.size)


@router.get(
    "/data",
    response_model=PageApiResponse[SearchResultResponse],
    summary="학습 데이터 검색",
    description="정제·통합 완료된 학습 데이터를 다양한 조건으로 검색한다. "
    "Selection(촬영 시간, 온도, 헤드라이트), ODD(날씨, 시간대, 노면), "
    "Label(객체 클래스, 최소 객체 수, 최소 신뢰도) 조건을 조합할 수 있다. "
    "페이징은 offset(page) 또는 cursor(after) 방식을 지원한다.",
    responses={
        200: {"description": "학습 데이터 목록 (Selection + OddTag + Labels 통합)"},
        400: {"model": ProblemDetail, "description": "잘못된 파라미터 (page + after 동시 사용, 유효하지 않은 Enum 등)"},
        500: {"model": ProblemDetail, "description": "서버 내부 오류"},
    },
)
def search_data(
    request: DataSearchRequest = Depends(),
    service: DataReadService = Depends(get_data_read_service),
):
    criteria = DataSearchCriteriaMapper.to_domain(request)
    results, total = service.search(criteria)
    items = [SearchResultResponseMapper.from_domain(r) for r in results]

    if request.after is not None:
        last_id = results[-1].selection.id.value if results else None
        return PageApiResponse.of_cursor(items=items, size=request.size, last_id=last_id)
    return PageApiResponse.of(items=items, total=total, page=request.page, size=request.size)

from fastapi import APIRouter, Depends
from starlette.responses import JSONResponse

from app.adapter.inbound.rest.mappers import (
    RejectionCriteriaMapper,
    RejectionResponseMapper,
    SearchCriteriaMapper,
    SearchResultResponseMapper,
    TaskResponseMapper,
)
from app.adapter.inbound.rest.schemas import (
    ApiResponse,
    DataSearchRequest,
    PageApiResponse,
    RejectionResponse,
    RejectionSearchRequest,
    SearchResultResponse,
    TaskResponse,
    TaskSubmitResponse,
)
from app.application.analysis_service import AnalysisService
from app.application.rejection_service import RejectionService
from app.application.search_service import SearchService
from app.application.task_service import TaskService
from app.domain.enums import TaskStatus
from app.dependencies import (
    get_analysis_service,
    get_rejection_service,
    get_search_service,
    get_task_service,
)

router = APIRouter()


@router.post("/analyze", status_code=202, response_model=ApiResponse[TaskSubmitResponse])
def analyze(service: AnalysisService = Depends(get_analysis_service)):
    """3개 파일을 읽어 MongoDB에 적재하고 비동기 정제 파이프라인을 시작한다."""
    task_id = service.submit()

    return JSONResponse(
        status_code=202,
        content=ApiResponse(
            data=TaskSubmitResponse(task_id=task_id, status=TaskStatus.PENDING),
        ).model_dump(),
    )


@router.get("/analyze/{task_id}", response_model=ApiResponse[TaskResponse])
def get_task_status(
    task_id: str,
    service: TaskService = Depends(get_task_service),
):
    """분석 작업의 진행 상태를 조회한다."""
    task = service.get_task(task_id)
    return ApiResponse(data=TaskResponseMapper.from_domain(task))


@router.get("/rejections", response_model=PageApiResponse[RejectionResponse])
def get_rejections(
    request: RejectionSearchRequest = Depends(),
    service: RejectionService = Depends(get_rejection_service),
):
    """정제 과정에서 거부된 데이터 목록을 조회한다."""
    criteria = RejectionCriteriaMapper.to_domain(request)
    rejections, total = service.search(criteria)
    items = [RejectionResponseMapper.from_domain(r) for r in rejections]
    return PageApiResponse.of(items=items, total=total, page=request.page, size=request.size)


@router.get("/search", response_model=PageApiResponse[SearchResultResponse])
def search(
    request: DataSearchRequest = Depends(),
    service: SearchService = Depends(get_search_service),
):
    """학습 데이터를 조건에 맞게 검색한다."""
    criteria = SearchCriteriaMapper.to_domain(request)
    results, total = service.search(criteria)
    items = [SearchResultResponseMapper.from_domain(r) for r in results]
    return PageApiResponse.of(items=items, total=total, page=request.page, size=request.size)

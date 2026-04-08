from fastapi import APIRouter, Depends

from app.adapter.inbound.mappers import (
    AnalysisResponseMapper,
    RejectionCriteriaMapper,
    RejectionResponseMapper,
    SearchCriteriaMapper,
    SearchResultResponseMapper,
)
from app.adapter.inbound.schemas import (
    AnalysisResponse,
    ApiResponse,
    DataSearchRequest,
    PageApiResponse,
    RejectionResponse,
    RejectionSearchRequest,
    SearchResultResponse,
)
from app.application.analysis_service import AnalysisService
from app.application.rejection_service import RejectionService
from app.application.search_service import SearchService
from app.dependencies import get_analysis_service, get_rejection_service, get_search_service

router = APIRouter()


@router.post("/analyze", response_model=ApiResponse[AnalysisResponse])
def analyze(service: AnalysisService = Depends(get_analysis_service)):
    """3개 파일을 읽어 정제 → 적재 → 분석 결과를 반환한다."""
    result = service.analyze()
    return ApiResponse(data=AnalysisResponseMapper.from_domain(result))


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

from app.adapter.inbound.schemas import (
    AnalysisResponse,
    DataSearchRequest,
    LabelResponse,
    RejectionResponse,
    RejectionSearchRequest,
    SearchResultResponse,
    StageResultResponse,
)
from app.domain.models import AnalysisResult, Rejection, RejectionCriteria, SearchCriteria
from app.domain.ports import SearchResult


class AnalysisResponseMapper:
    @staticmethod
    def from_domain(result: AnalysisResult) -> AnalysisResponse:
        return AnalysisResponse(
            selection=StageResultResponse(
                total=result.selection.total,
                loaded=result.selection.loaded,
                rejected=result.selection.rejected,
            ),
            odd_tagging=StageResultResponse(
                total=result.odd_tagging.total,
                loaded=result.odd_tagging.loaded,
                rejected=result.odd_tagging.rejected,
            ),
            auto_labeling=StageResultResponse(
                total=result.auto_labeling.total,
                loaded=result.auto_labeling.loaded,
                rejected=result.auto_labeling.rejected,
            ),
            fully_linked=result.fully_linked,
            partial=result.partial,
        )


class RejectionResponseMapper:
    @staticmethod
    def from_domain(rejection: Rejection) -> RejectionResponse:
        return RejectionResponse(
            record_identifier=rejection.record_identifier,
            stage=rejection.stage.value,
            reason=rejection.reason.value,
            detail=rejection.detail,
            raw_data=rejection.raw_data,
            created_at=rejection.created_at,
        )


class SearchResultResponseMapper:
    @staticmethod
    def from_domain(result: SearchResult) -> SearchResultResponse:
        return SearchResultResponse(
            video_id=result.selection.id,
            recorded_at=result.selection.recorded_at,
            temperature_celsius=result.selection.temperature_celsius,
            wiper_active=result.selection.wiper_active,
            wiper_level=result.selection.wiper_level,
            headlights_on=result.selection.headlights_on,
            source_path=result.selection.source_path,
            weather=result.odd_tag.weather.value if result.odd_tag else None,
            time_of_day=result.odd_tag.time_of_day.value if result.odd_tag else None,
            road_surface=result.odd_tag.road_surface.value if result.odd_tag else None,
            labels=[
                LabelResponse(
                    object_class=lb.object_class.value,
                    obj_count=lb.obj_count,
                    avg_confidence=lb.avg_confidence,
                )
                for lb in result.labels
            ],
        )


class RejectionCriteriaMapper:
    @staticmethod
    def to_domain(request: RejectionSearchRequest) -> RejectionCriteria:
        return RejectionCriteria(
            stage=request.stage,
            reason=request.reason,
            page=request.page,
            size=request.size,
        )


class SearchCriteriaMapper:
    @staticmethod
    def to_domain(request: DataSearchRequest) -> SearchCriteria:
        return SearchCriteria(
            weather=request.weather,
            time_of_day=request.time_of_day,
            road_surface=request.road_surface,
            object_class=request.object_class,
            min_obj_count=request.min_obj_count,
            min_confidence=request.min_confidence,
            page=request.page,
            size=request.size,
        )
